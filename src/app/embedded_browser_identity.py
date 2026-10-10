from __future__ import annotations

import secrets
from urllib.parse import urlencode

from app.browser_identity import BrowserIdentity
from app.config import AppSettings
from mcpgtw.oauth.authorization_server import EmbeddedAuthorizationServer


class EmbeddedBrowserIdentity(BrowserIdentity):
    def __init__(self, settings: AppSettings, server: EmbeddedAuthorizationServer) -> None:
        self.settings = settings
        self.server = server

    async def authorization_url(self, state: str, nonce: str, challenge: str) -> str:
        return (
            self.server.issuer
            + "/oauth/authorize?"
            + urlencode(
                {
                    "response_type": "code",
                    "client_id": self.settings.oidc_client_id,
                    "redirect_uri": self.settings.public_base_url + "/app/oauth/callback",
                    "scope": "openid",
                    "state": state,
                    "nonce": nonce,
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                }
            )
        )

    async def exchange(self, code: str, verifier: str, nonce: str) -> tuple[str, str]:
        client = await self.server.clients.get(self.settings.oidc_client_id)

        if client is None or not secrets.compare_digest(
            client["secret"].encode(), self.settings.oidc_client_secret.get_secret_value().encode()
        ):
            raise ValueError("Invalid browser client")

        result = await self.server.exchange(
            client,
            {
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
                "redirect_uri": self.settings.public_base_url + "/app/oauth/callback",
            },
        )

        if result is None:
            raise ValueError("Invalid browser authorization")

        claims = self.server.key.decode(
            result["id_token"], self.server.issuer, client["client_id"], "JWT"
        )

        if not secrets.compare_digest(claims["nonce"].encode(), nonce.encode()):
            raise ValueError("Invalid browser nonce")

        return claims["iss"], claims["sub"]
