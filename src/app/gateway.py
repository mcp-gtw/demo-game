from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import re
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response
from starlette.types import Scope

from app.catalog import build_catalog
from app.config import AppSettings, get_app_settings
from app.provider import LocalProvider
from app.room_manager import RoomManager
from app.session import Session
from app.tools import TOOL_DEFINITIONS
from mcp_gtw.channel import Channel
from mcp_gtw.config import GatewaySettings
from mcp_gtw.errors import ChannelCapacityError
from mcp_gtw.gateway import Gateway

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
    streams the world. Closing the browser tears the session and its player down.
    """

    mcp_server_name = "app"

    def __init__(
        self,
        settings: GatewaySettings | None = None,
        app_settings: AppSettings | None = None,
    ) -> None:
        self.app_settings = app_settings or get_app_settings()
        self.rooms = RoomManager(self.app_settings)
        self._sessions: dict[str, Session] = {}
        self._session_lock = asyncio.Lock()
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
        return FileResponse(WEB_DIR / "dist" / "index.html")

    def register_routes(self, app: FastAPI) -> None:
        super().register_routes(app)
        app.add_api_route("/app/info", self.info, methods=["GET"])
        app.add_api_websocket_route("/app/stream", self.stream_endpoint)
        app.mount("/static", RevalidatingStaticFiles(directory=WEB_DIR), name="static")

    async def info(self) -> dict[str, Any]:
        return {
            "playersOnline": sum(len(room.world.players) for room in self.rooms.all()),
            "tools": [
                {"name": tool["name"], "description": tool["description"]}
                for tool in TOOL_DEFINITIONS
            ],
        }

    async def stream_endpoint(self, websocket: WebSocket) -> None:
        await websocket.accept()
        session = await self._acquire_session(websocket.query_params.get("token"))

        if session is None:
            await websocket.close(code=1008)
            return

        self._session_connect(session)

        try:
            await websocket.send_json(self._session_message(websocket, session))
            await self._run_session(websocket, session)
        except WebSocketDisconnect:
            pass
        finally:
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
                channel_id=channel_id, mcp_token=f"mcp-{token}", ttl_seconds=float("inf")
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
        try:
            message = json.loads(text)
        except json.JSONDecodeError:
            return

        kind = message.get("type")

        if kind == "ping":
            await websocket.send_json({"type": "pong", "id": message.get("id")})
        elif kind == "me" and session.player_id is not None:
            state = session.room.game.player_state(session.player_id)

            if state is not None:
                await websocket.send_json({"type": "me", "player": state})

    def _session_message(self, websocket: WebSocket, session: Session) -> dict[str, Any]:
        http_scheme = "https" if websocket.url.scheme == "wss" else "http"
        host = websocket.url.netloc

        return {
            "type": "session",
            "mcpUrl": f"{http_scheme}://{host}/mcp/{session.channel_id}",
            "mcpToken": session.mcp_token,
        }

    def _session_connect(self, session: Session) -> None:
        session.connections += 1

    def _session_disconnect(self, session: Session) -> None:
        session.connections -= 1

        if session.connections <= 0:
            session.teardown = asyncio.create_task(self._teardown_after_grace(session))

    async def _teardown_after_grace(self, session: Session) -> None:
        try:
            await asyncio.sleep(self.app_settings.session_grace_seconds)
        except asyncio.CancelledError:
            return

        # take the lock so a concurrent reconnect never reuses a session being reclaimed
        async with self._session_lock:
            if self._sessions.get(session.channel_id) is not session:
                return

            self._sessions.pop(session.channel_id, None)

            if session.player_id is not None:
                session.room.world.remove_player(session.player_id)

            await self.registry.remove_channel(session.channel_id)

    @staticmethod
    async def _cancel(task: asyncio.Task[Any]) -> None:
        task.cancel()

        with contextlib.suppress(asyncio.CancelledError):
            await task
