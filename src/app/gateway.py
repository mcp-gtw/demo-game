from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import re
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope

from app.browser_identity import BrowserIdentity, OidcBrowserIdentity
from app.browser_oauth import BrowserOAuth
from app.browser_session import BrowserSessionStore
from app.catalog import build_catalog
from app.config import AppSettings, get_app_settings
from app.embedded_browser_identity import EmbeddedBrowserIdentity
from app.game_consent_policy import GameConsentPolicy
from app.gateway_settings import AppGatewaySettings
from app.oauth_websocket import OAuthWebSocket
from app.provider import LocalProvider
from app.room_manager import RoomManager
from app.session import Session
from app.tools import TOOL_DEFINITIONS
from mcpgtw.channel import Channel
from mcpgtw.config import GatewaySettings
from mcpgtw.errors import ChannelCapacityError, GatewayConfigurationError
from mcpgtw.gateway import Gateway
from mcpgtw.oauth.authorization_server import EmbeddedAuthorizationServer
from mcpgtw.oauth.channel_access import DenyUnlessGranted
from mcpgtw.oauth.channel_grants import ChannelGrantStore
from mcpgtw.oauth.client_registry import OAuthClientRegistry
from mcpgtw.oauth.identity import SqlitePasswordIdentity
from mcpgtw.oauth.signing_key import OAuthSigningKey
from mcpgtw.oauth.sqlite_grants import SqliteChannelGrantStore
from mcpgtw.oauth.state_store import SqliteOAuthStateStore
from mcpgtw.oauth.token_verifier import AccessTokenVerifier

logger = logging.getLogger(__name__)

WEB_DIR = Path(__file__).parent / "web"

_TOKEN_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _channel_id_for(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()[:16]


class RevalidatingStaticFiles(StaticFiles):
    """Serves the client with must-revalidate so a fresh build is never masked by the cache."""

    async def get_response(self, path: str, scope: Scope) -> Response:
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


class AppGateway(Gateway):
    """The game application: an authoritative world served through server-side MCP tools.

    Each browser opens one session websocket that gives it a private MCP channel. The agent connects
    to that channel and calls login, the session adopts the player, and the same websocket then
    streams the world. Browser connections and successful MCP calls retain the session.
    """

    mcp_server_name = "app"
    browser_oauth_class: type[BrowserOAuth] = BrowserOAuth

    def __init__(
        self,
        app_settings: AppSettings | None = None,
        *,
        gateway_settings: GatewaySettings | None = None,
        browser_identity: BrowserIdentity | None = None,
        browser_sessions: BrowserSessionStore | None = None,
        channel_grants: ChannelGrantStore | None = None,
        access_token_verifier: AccessTokenVerifier | None = None,
    ) -> None:
        self.app_settings = app_settings or get_app_settings()
        self.rooms = RoomManager(self.app_settings)
        self._sessions: dict[str, Session] = {}
        self._oauth_owners: dict[tuple[str, str], str] = {}
        self._session_lock = asyncio.Lock()
        settings = gateway_settings or AppGatewaySettings()
        mode = self.app_settings.mcp_auth_mode
        self._owned_browser_identity: OidcBrowserIdentity | None = None
        self.browser_oauth: BrowserOAuth | None = None
        self.channel_grants = channel_grants

        if mode != "legacy":
            if (
                settings.oauth_mode == "off"
                or settings.oauth_allow_static_mcp_tokens != (mode == "dual")
                or self.app_settings.oidc_issuer not in settings.oauth_authorization_servers
                or settings.oauth_resource_url != self.app_settings.public_base_url + "/mcp"
            ):
                raise GatewayConfigurationError("Inconsistent game and gateway OAuth configuration")

            self.channel_grants = channel_grants or SqliteChannelGrantStore(
                self.app_settings.oauth_database_path
            )
            embedded = None

            if settings.oauth_mode == "embedded":
                store = SqliteOAuthStateStore(self.app_settings.oauth_database_path)
                clients = OAuthClientRegistry(
                    store,
                    settings.oauth_embedded_issuer,
                    settings.oauth_resource_url,
                    settings.oauth_embedded_dcr_enabled,
                )
                clients.add(
                    self.app_settings.oidc_client_id,
                    {
                        "client_name": "MCP Game browser",
                        "redirect_uris": [
                            self.app_settings.public_base_url + "/app/oauth/callback"
                        ],
                        "token_endpoint_auth_method": "client_secret_basic",
                        "response_types": ["code"],
                        "grant_types": ["authorization_code"],
                    },
                    self.app_settings.oidc_client_secret.get_secret_value(),
                    browser=True,
                )
                embedded = EmbeddedAuthorizationServer(
                    settings,
                    SqlitePasswordIdentity(
                        self.app_settings.oauth_database_path,
                        self.app_settings.oauth_account_registration_enabled,
                    ),
                    GameConsentPolicy(self),
                    store,
                    OAuthSigningKey(self.app_settings.oauth_database_path + ".key"),
                    clients,
                )
                browser_identity = browser_identity or EmbeddedBrowserIdentity(
                    self.app_settings, embedded
                )

            elif not self.app_settings.oauth_mcp_client_ids:
                raise GatewayConfigurationError("External OAuth requires approved MCP client IDs")

            super().__init__(
                settings,
                authorization_server=embedded,
                access_token_verifier=access_token_verifier,
                channel_access=DenyUnlessGranted(self.channel_grants),
                static_channel_eligible=lambda channel: (
                    channel.metadata.get("auth_method") == "token"
                ),
            )
            if browser_identity is None:
                self._owned_browser_identity = OidcBrowserIdentity(self.app_settings)
                browser_identity = self._owned_browser_identity

            self.browser_oauth = self.browser_oauth_class(
                self,
                browser_identity,
                browser_sessions or BrowserSessionStore(self.app_settings.oauth_database_path),
            )
        else:
            if settings.oauth_mode != "off":
                raise GatewayConfigurationError("Legacy game mode requires OAuth off")

            super().__init__(settings)

    @contextlib.asynccontextmanager
    async def serve(self) -> AsyncIterator[None]:
        dt = 1.0 / self.app_settings.tick_rate
        simulation = asyncio.create_task(self._run_simulation(dt))

        try:
            yield
        finally:
            teardowns = [s.teardown for s in self._sessions.values() if s.teardown is not None]

            for teardown in teardowns:
                teardown.cancel()

            simulation.cancel()

            await asyncio.gather(simulation, *teardowns, return_exceptions=True)

            if self._owned_browser_identity is not None:
                await self._owned_browser_identity.client.aclose()

    async def _run_simulation(self, dt: float) -> None:
        while True:
            for room in self.rooms.all():
                try:
                    room.world.tick(dt)
                    await room.hub.broadcast({"type": "snapshot", "world": room.world.snapshot()})
                except Exception:
                    logger.exception("Simulation tick failed for room %s", room.id)

            await asyncio.sleep(dt)

    async def home(self) -> FileResponse:
        headers = {}

        if self.browser_oauth is not None:
            websocket_origin = self.app_settings.public_base_url.replace(
                "https://", "wss://", 1
            ).replace("http://", "ws://", 1)
            headers = {
                "Content-Security-Policy": (
                    "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                    "img-src 'self' data: blob:; media-src 'self' blob:; "
                    f"connect-src 'self' {websocket_origin}; "
                    "object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
                ),
                "Referrer-Policy": "no-referrer",
                "X-Content-Type-Options": "nosniff",
            }

        return FileResponse(WEB_DIR / "dist" / "index.html", headers=headers)

    def register_routes(self, app: FastAPI) -> None:
        super().register_routes(app)
        if self.browser_oauth is not None:
            self.browser_oauth.register_routes(app)

        app.add_api_route("/app/info", self.info, methods=["GET"])
        app.add_api_websocket_route("/app/stream", self.stream_endpoint)
        app.mount("/static", RevalidatingStaticFiles(directory=WEB_DIR), name="static")

    async def info(self) -> dict[str, Any]:
        return {
            "authMethods": ["token"]
            if self.app_settings.mcp_auth_mode == "legacy"
            else ["oauth"]
            if self.app_settings.mcp_auth_mode == "oauth"
            else ["token", "oauth"],
            "oauthMcpUrl": self.settings.oauth_resource_url
            if self.browser_oauth is not None
            else None,
            "playersOnline": sum(len(room.world.players) for room in self.rooms.all()),
            "tools": [
                {"name": tool["name"], "description": tool["description"]}
                for tool in TOOL_DEFINITIONS
            ],
        }

    async def stream_endpoint(self, websocket: WebSocket) -> None:
        token = websocket.query_params.get("token")
        ticket = websocket.query_params.get("ticket")

        if "token" in websocket.query_params and "ticket" in websocket.query_params:
            await websocket.close(code=1008)
            return

        if ticket and self.browser_oauth is not None:
            session = await self.browser_oauth.consume_ticket(websocket, ticket)
        elif self.app_settings.mcp_auth_mode != "oauth" and not ticket:
            session = await self._acquire_session(token)
        else:
            session = None

        if session is None:
            await websocket.close(code=1008)
            return

        if session.auth_method == "oauth":
            original = websocket

            async def authorized() -> bool:
                browser = await self.browser_oauth.store.get(
                    "session", original.cookies.get(self.app_settings.session_cookie_name, "")
                )
                return (
                    browser is not None
                    and browser["consented"]
                    and self.registry.get(session.channel_id) is not None
                )

            websocket = OAuthWebSocket(original, authorized)

        await websocket.accept()
        self._session_connect(session)

        try:
            await websocket.send_json(self._session_message(websocket, session))
            await self._run_session(websocket, session)
        except WebSocketDisconnect:
            pass
        finally:
            if self.browser_oauth is not None:
                self.browser_oauth.disconnected(
                    original if session.auth_method == "oauth" else websocket, session.channel_id
                )

            session.room.hub.unsubscribe(websocket)
            self._session_disconnect(session)

    async def _acquire_session(self, token: str | None) -> Session | None:
        if token is None or _TOKEN_PATTERN.match(token) is None:
            return None

        channel_id = _channel_id_for(token)

        # serialize so two connects with the same token converge on one session and channel
        async with self._session_lock:
            session = self._sessions.get(channel_id)

            if session is not None:
                if session.teardown is not None:
                    session.teardown.cancel()
                    session.teardown = None

                return session

            channel = await self._identity_channel(channel_id, token)

            if channel is None:
                return None

            session = Session(
                channel_id=channel_id, mcp_token=channel.mcp_token, room=self.rooms.default
            )
            await LocalProvider(channel, session).start()
            self._sessions[channel_id] = session
            return session

    async def _identity_channel(self, channel_id: str, token: str) -> Channel | None:
        existing = self.registry.get(channel_id)

        if existing is not None:
            return existing

        try:
            return await self.create_channel(
                channel_id=channel_id,
                mcp_token=f"mcp-{token}",
                ttl_seconds=float("inf"),
                metadata={"auth_method": "token"},
            )
        except ChannelCapacityError:
            return self.registry.get(channel_id)

    async def _run_session(self, websocket: WebSocket, session: Session) -> None:
        if not session.logged_in.is_set():
            await self._wait_for_login(websocket, session)

        await self._start_game(websocket, session)

        while True:
            await self._handle_message(websocket, session, await websocket.receive_text())

    async def _wait_for_login(self, websocket: WebSocket, session: Session) -> None:
        waiter = asyncio.ensure_future(session.logged_in.wait())

        try:
            while not session.logged_in.is_set():
                receiver = asyncio.ensure_future(websocket.receive_text())
                done, _ = await asyncio.wait(
                    {receiver, waiter}, return_when=asyncio.FIRST_COMPLETED
                )

                if receiver in done:
                    await self._handle_message(websocket, session, receiver.result())
                else:
                    await self._cancel(receiver)
        finally:
            await self._cancel(waiter)

    async def _start_game(self, websocket: WebSocket, session: Session) -> None:
        room = session.room
        player = room.world.players[session.player_id]
        login = {"type": "login", "player": {"id": player.id, "name": player.name}}
        await websocket.send_json(login)
        await websocket.send_json({"type": "catalog", "catalog": build_catalog(self.app_settings)})
        await websocket.send_json({"type": "map", "map": room.world.map.to_public()})
        await websocket.send_json({"type": "snapshot", "world": room.world.snapshot()})
        room.hub.subscribe(websocket)

    async def _handle_message(self, websocket: WebSocket, session: Session, text: str) -> None:
        if len(text.encode()) > 4096:
            return

        try:
            message = json.loads(text)
        except json.JSONDecodeError:
            return

        if not isinstance(message, dict):
            return

        kind = message.get("type")

        if kind == "ping":
            await websocket.send_json({"type": "pong", "id": message.get("id")})
        elif kind == "me" and session.player_id is not None:
            state = session.room.game.player_state(session.player_id)

            if state is not None:
                await websocket.send_json({"type": "me", "player": state})

    def _session_message(self, websocket: WebSocket, session: Session) -> dict[str, Any]:
        if session.auth_method == "oauth":
            return {
                "type": "session",
                "authMethod": "oauth",
                "mcpUrl": self.settings.oauth_resource_url + "/" + session.channel_id,
            }

        if self.app_settings.public_base_url:
            return {
                "type": "session",
                "mcpUrl": self.app_settings.public_base_url + "/mcp/" + session.channel_id,
                "mcpToken": session.mcp_token,
            }

        http_scheme = "https" if websocket.url.scheme == "wss" else "http"
        host = websocket.url.netloc

        return {
            "type": "session",
            "mcpUrl": f"{http_scheme}://{host}/mcp/{session.channel_id}",
            "mcpToken": session.mcp_token,
        }

    async def acquire_oauth_session(self, issuer: str, subject: str) -> Session:
        async with self._session_lock:
            owner = (issuer, subject)
            channel_id = self._oauth_owners.get(owner)
            existing = self._sessions.get(channel_id)

            if existing is not None:
                return existing

            channel = await self.create_channel(
                metadata={"auth_method": "oauth"}, ttl_seconds=float("inf")
            )
            session = Session(channel.channel_id, "", self.rooms.default, auth_method="oauth")
            await LocalProvider(channel, session).start()
            self._sessions[channel.channel_id] = session
            self._oauth_owners[owner] = channel.channel_id
            self.schedule_idle_teardown(session, self.app_settings.session_idle_seconds)
            return session

    async def revoke_oauth_channel(self, channel_id: str) -> None:
        async with self._session_lock:
            session = self._sessions.get(channel_id)

            if session is None or session.auth_method != "oauth":
                return

            self._sessions.pop(channel_id)

            if session.teardown is not None:
                session.teardown.cancel()

            if session.player_id is not None:
                session.room.world.remove_player(session.player_id)

            await self.registry.remove_channel(channel_id)

    async def on_channel_removed(self, channel: Channel) -> None:
        await super().on_channel_removed(channel)

        if self.channel_grants is not None:
            await self.channel_grants.remove_channel(channel.channel_id)

        if isinstance(self.authorization_server, EmbeddedAuthorizationServer):
            for owner, owned_channel in self._oauth_owners.items():
                if owned_channel == channel.channel_id:
                    await self.authorization_server.store.revoke_subject(owner[1])

        self._oauth_owners = {
            owner: cid for owner, cid in self._oauth_owners.items() if cid != channel.channel_id
        }

    def schedule_idle_teardown(self, session: Session, delay_seconds: float) -> None:
        if session.teardown is not None:
            session.teardown.cancel()

        session.teardown = asyncio.create_task(self._teardown_when_idle(session, delay_seconds))

    def _session_connect(self, session: Session) -> None:
        if session.teardown is not None:
            session.teardown.cancel()
            session.teardown = None

        session.connections += 1

    def _session_disconnect(self, session: Session) -> None:
        session.connections -= 1

        if session.connections <= 0:
            delay = max(self.app_settings.session_grace_seconds, self._mcp_idle_remaining(session))
            self.schedule_idle_teardown(session, delay)

    def _mcp_idle_remaining(self, session: Session) -> float:
        if session.last_mcp_activity is None:
            return 0

        return session.last_mcp_activity + self.app_settings.session_idle_seconds - time.monotonic()

    async def _teardown_when_idle(self, session: Session, delay_seconds: float) -> None:
        while True:
            try:
                await asyncio.sleep(delay_seconds)
            except asyncio.CancelledError:
                return

            async with self._session_lock:
                if self._sessions.get(session.channel_id) is not session or session.connections > 0:
                    return

                delay_seconds = self._mcp_idle_remaining(session)

                if delay_seconds > 0:
                    continue

                self._sessions.pop(session.channel_id)

                if session.player_id is not None:
                    session.room.world.remove_player(session.player_id)

                await self.registry.remove_channel(session.channel_id)
                return

    @staticmethod
    async def _cancel(task: asyncio.Task[Any]) -> None:
        task.cancel()

        with contextlib.suppress(asyncio.CancelledError):
            await task
