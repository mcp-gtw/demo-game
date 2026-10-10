from __future__ import annotations

import secrets
from abc import ABC, abstractmethod
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt

from app.config import AppSettings
from mcpgtw.config import validate_oauth_url
from mcpgtw.oauth.http_fetch import bounded_json


class BrowserIdentity(ABC):
    @abstractmethod
    async def authorization_url(self, state: str, nonce: str, challenge: str) -> str: ...

    @abstractmethod
    async def exchange(self, code: str, verifier: str, nonce: str) -> tuple[str, str]: ...


class OidcBrowserIdentity(BrowserIdentity):
    def __init__(self, settings: AppSettings, client: httpx.AsyncClient | None = None) -> None:
        self.settings = settings
        self.client = client or httpx.AsyncClient(
            timeout=5, trust_env=False, follow_redirects=False
        )
        self._metadata: dict[str, Any] | None = None

    async def _discovery(self) -> dict[str, Any]:
        if self._metadata is None:
            data = await bounded_json(
                self.client,
                "GET",
                self.settings.oidc_issuer.rstrip("/") + "/.well-known/openid-configuration",
                65536,
            )

            if data.get("issuer") != self.settings.oidc_issuer or "S256" not in data.get(
                "code_challenge_methods_supported", []
            ):
                raise ValueError("Invalid identity provider metadata")

            for key in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
                validate_oauth_url(data[key], self.settings.oauth_allow_localhost_http)

            self._metadata = data

        return self._metadata

    async def authorization_url(self, state: str, nonce: str, challenge: str) -> str:
        metadata = await self._discovery()
        params = {
            "response_type": "code",
            "client_id": self.settings.oidc_client_id,
            "redirect_uri": self.settings.public_base_url + "/app/oauth/callback",
            "scope": "openid",
            "state": state,
            "nonce": nonce,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        return metadata["authorization_endpoint"] + "?" + urlencode(params)

    async def exchange(self, code: str, verifier: str, nonce: str) -> tuple[str, str]:
        metadata = await self._discovery()
        data = await bounded_json(
            self.client,
            "POST",
            metadata["token_endpoint"],
            65536,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": self.settings.public_base_url + "/app/oauth/callback",
                "client_id": self.settings.oidc_client_id,
            },
            auth=(
                self.settings.oidc_client_id,
                self.settings.oidc_client_secret.get_secret_value(),
            ),
        )
        token = data["id_token"]

        if not isinstance(token, str) or len(token) > 8192:
            raise ValueError("Invalid identity token")

        header = jwt.get_unverified_header(token)

        if (
            header.get("alg") not in ("RS256", "ES256")
            or "jku" in header
            or "x5u" in header
            or "crit" in header
        ):
            raise ValueError("Invalid identity token algorithm")

        jwks = await bounded_json(self.client, "GET", metadata["jwks_uri"], 65536)
        keys = jwks.get("keys", [])

        if not isinstance(keys, list) or len(keys) > 64:
            raise ValueError("Invalid key set")

        key = next(
            (jwt.PyJWK.from_dict(item) for item in keys if item.get("kid") == header.get("kid")),
            None,
        )

        if key is None or key.algorithm_name != header["alg"]:
            raise ValueError("Unknown identity signing key")

        claims = jwt.decode(
            token,
            key.key,
            algorithms=[header["alg"]],
            issuer=self.settings.oidc_issuer,
            audience=self.settings.oidc_client_id,
            options={"require": ["exp", "iat", "sub", "iss", "aud", "nonce"]},
        )

        if (
            not isinstance(claims["sub"], str)
            or not claims["sub"]
            or not secrets.compare_digest(str(claims["nonce"]), nonce)
            or ("azp" in claims and claims["azp"] != self.settings.oidc_client_id)
            or (isinstance(claims["aud"], list) and len(claims["aud"]) > 1 and "azp" not in claims)
        ):
            raise ValueError("Invalid identity claims")

        return claims["iss"], claims["sub"]
