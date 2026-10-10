from __future__ import annotations

import base64
import hashlib
import secrets
import time
from typing import TYPE_CHECKING

from fastapi import FastAPI, Request, WebSocket
from starlette.responses import JSONResponse, RedirectResponse, Response

from app.browser_cookie import browser_cookie
from app.browser_identity import BrowserIdentity
from app.browser_session import BrowserSessionStore
from mcpgtw.oauth.rate_limit import OAuthRateLimitPolicy, WindowOAuthRateLimitPolicy
from mcpgtw.oauth.verified_principal import VerifiedPrincipal

if TYPE_CHECKING:
    from app.gateway import AppGateway
    from app.session import Session


class BrowserOAuth:
    rate_limit_class: type[OAuthRateLimitPolicy] = WindowOAuthRateLimitPolicy

    def __init__(
        self,
        gateway: AppGateway,
        identity: BrowserIdentity,
        store: BrowserSessionStore,
        *,
        rate_limit: OAuthRateLimitPolicy | None = None,
        principal_limit: OAuthRateLimitPolicy | None = None,
    ) -> None:
        self.gateway = gateway
        self.identity = identity
        self.store = store
        self.settings = gateway.app_settings

        def budget() -> OAuthRateLimitPolicy:
            return self.rate_limit_class(
                self.settings.oauth_browser_rate_limit_requests,
                self.settings.oauth_browser_rate_limit_window_seconds,
                self.settings.oauth_browser_rate_limit_maximum_keys,
                gateway.settings.oauth_rate_limit_backoff_seconds,
                gateway.settings.oauth_rate_limit_maximum_backoff_seconds,
            )

        self.rate_limit = rate_limit or budget()
        self.principal_limit = principal_limit or budget()
        self._sockets: dict[str, set[WebSocket]] = {}

    def register_routes(self, app: FastAPI) -> None:
        app.add_api_route("/app/oauth/login", self.login, methods=["GET"])
        app.add_api_route("/app/oauth/callback", self.callback, methods=["GET"])
        app.add_api_route("/app/oauth/consent", self.consent, methods=["POST"])
        app.add_api_route("/app/oauth/ticket", self.ticket, methods=["POST"])
        app.add_api_route("/app/oauth/logout", self.logout, methods=["POST"])

    @staticmethod
    def _denied() -> JSONResponse:
        return JSONResponse(
            {"error": "Authentication required"},
            status_code=403,
            headers={"Cache-Control": "no-store"},
        )

    def _cookie(self, response: Response, name: str, value: str, ttl: int) -> None:
        response.set_cookie(
            name, value, max_age=ttl, secure=True, httponly=True, samesite="lax", path="/app"
        )
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"

    async def login(self, request: Request) -> Response:
        self.rate_limit.enforce(request.client.host if request.client else "unknown")

        verifier = secrets.token_urlsafe(48)
        nonce = secrets.token_urlsafe(32)
        try:
            state = await self.store.put("login", {"verifier": verifier, "nonce": nonce}, 120)
            challenge = (
                base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
                .rstrip(b"=")
                .decode()
            )

            url = await self.identity.authorization_url(state, nonce, challenge)
        except Exception:
            return self._denied()

        response = RedirectResponse(url)
        self._cookie(response, "game_oauth_state", state, 120)
        return response

    async def callback(self, request: Request) -> Response:
        self.rate_limit.enforce(request.client.host if request.client else "unknown")

        state = request.query_params.get("state", "")
        cookie = browser_cookie(request, "game_oauth_state")

        if (
            not state
            or not cookie
            or not secrets.compare_digest(state.encode(), cookie.encode())
            or any(
                len(request.query_params.getlist(name)) != 1 for name in ("state", "code", "iss")
            )
            or request.query_params.get("iss") != self.settings.oidc_issuer
        ):
            return self._denied()

        transaction = await self.store.consume("login", state)

        if transaction is None:
            return self._denied()

        try:
            issuer, subject = await self.identity.exchange(
                request.query_params["code"], transaction["verifier"], transaction["nonce"]
            )

            if issuer != self.settings.oidc_issuer:
                return self._denied()

        except Exception:
            return self._denied()

        self.principal_limit.enforce(self._principal(issuer, subject))

        try:
            old = await self.store.consume(
                "session", browser_cookie(request, self.settings.session_cookie_name)
            )

            if old is not None and (old["issuer"], old["subject"]) != (issuer, subject):
                await self._revoke(old["channel"])

            session = await self.gateway.acquire_oauth_session(issuer, subject)
            cookie = await self.store.put(
                "session",
                {
                    "issuer": issuer,
                    "subject": subject,
                    "channel": session.channel_id,
                    "consented": False,
                    "expires_at": int(time.time() + self.settings.session_idle_seconds),
                },
                self.settings.session_idle_seconds,
            )
        except Exception:
            return self._denied()

        response = RedirectResponse(self.settings.public_base_url + "/?auth=oauth")
        self._cookie(
            response,
            self.settings.session_cookie_name,
            cookie,
            int(self.settings.session_idle_seconds),
        )
        response.delete_cookie(
            "game_oauth_state", path="/app", secure=True, httponly=True, samesite="lax"
        )
        return response

    async def _browser(self, request: Request) -> dict | None:
        self.rate_limit.enforce(request.client.host if request.client else "unknown")

        if request.headers.get("origin") not in self.settings.allowed_browser_origins:
            return None

        cookie = browser_cookie(request, self.settings.session_cookie_name)
        browser = await self.store.get("session", cookie)

        if browser is None or self.gateway.registry.get(browser["channel"]) is None:
            return None

        self.principal_limit.enforce(self._principal(browser["issuer"], browser["subject"]))
        return browser

    @staticmethod
    def _principal(issuer: str, subject: str) -> str:
        return hashlib.sha256((issuer + "\0" + subject).encode()).hexdigest()

    async def consent(self, request: Request) -> Response:
        browser = await self._browser(request)

        if browser is None:
            return self._denied()

        for client_id in self.settings.oauth_mcp_client_ids:
            principal = VerifiedPrincipal(
                browser["issuer"],
                browser["subject"],
                client_id,
                frozenset(self.gateway.settings.oauth_required_scopes),
                browser["expires_at"],
            )
            await self.gateway.channel_grants.grant(principal, browser["channel"])

        self.gateway._sessions[browser["channel"]].oauth_authorized_until = browser["expires_at"]
        browser["consented"] = True
        await self.store.update(
            "session", browser_cookie(request, self.settings.session_cookie_name), browser
        )
        return JSONResponse({"authorized": True}, headers={"Cache-Control": "no-store"})

    async def ticket(self, request: Request) -> Response:
        browser = await self._browser(request)

        if browser is None or not browser["consented"]:
            return self._denied()

        cookie = browser_cookie(request, self.settings.session_cookie_name)
        try:
            ticket = await self.store.put(
                "ticket",
                {"cookie": self.store._digest(cookie), "channel": browser["channel"]},
                self.settings.websocket_ticket_ttl_seconds,
            )
        except ValueError:
            return self._denied()

        return JSONResponse({"ticket": ticket}, headers={"Cache-Control": "no-store"})

    async def consume_ticket(self, websocket: WebSocket, ticket: str) -> Session | None:
        if websocket.headers.get("origin") not in self.settings.allowed_browser_origins:
            return None

        payload = await self.store.consume("ticket", ticket)
        cookie = browser_cookie(websocket, self.settings.session_cookie_name)
        browser = await self.store.get("session", cookie)

        if (
            payload is None
            or browser is None
            or not browser["consented"]
            or not secrets.compare_digest(payload["cookie"], self.store._digest(cookie))
            or payload["channel"] != browser["channel"]
        ):
            return None

        session = self.gateway._sessions.get(browser["channel"])

        if session is None or session.auth_method != "oauth":
            return None

        self._sockets.setdefault(session.channel_id, set()).add(websocket)
        return session

    def disconnected(self, websocket: WebSocket, channel_id: str) -> None:
        sockets = self._sockets.get(channel_id)

        if sockets is not None:
            sockets.discard(websocket)

            if not sockets:
                self._sockets.pop(channel_id, None)

    async def _revoke(self, channel_id: str) -> None:
        await self.gateway.revoke_oauth_channel(channel_id)

        for websocket in self._sockets.pop(channel_id, set()):
            await websocket.close(code=1008)

    async def logout(self, request: Request) -> Response:
        browser = await self._browser(request)

        if browser is None:
            return self._denied()

        await self.store.consume(
            "session", browser_cookie(request, self.settings.session_cookie_name)
        )
        await self._revoke(browser["channel"])
        response = JSONResponse({"loggedOut": True})
        self._cookie(response, self.settings.session_cookie_name, "", 0)
        response.delete_cookie(
            "oauth_login", path="/oauth", secure=True, httponly=True, samesite="lax"
        )
        return response
