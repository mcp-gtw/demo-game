from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.errors import AppError, CommandError
from app.game import GameService
from app.session import Session
from app.tools import TOOL_DEFINITIONS, dispatch
from mcp_gtw import protocol
from mcp_gtw.channel import Channel

logger = logging.getLogger(__name__)


class LocalProvider:
    """An in-process provider bound to one browser session.

    It answers the game tools directly against the world and, when the agent logs in, adopts the
    resulting player for its session so the browser can follow it. Each session may log in once.
    """

    def __init__(self, channel: Channel, session: Session) -> None:
        self.channel = channel
        self.session = session
        self._tasks: set[asyncio.Task[None]] = set()

    async def start(self) -> None:
        await self.channel.attach(self, provider_id="local", provider_name="game-server")
        await self.channel.register(protocol.TOOLS, TOOL_DEFINITIONS)

    async def send_json(self, message: dict[str, Any]) -> None:
        if message.get("type") != protocol.REQUEST:
            return

        task = asyncio.get_running_loop().create_task(self._handle(message))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        return None

    async def _handle(self, message: dict[str, Any]) -> None:
        request_id = message["requestId"]
        params = message.get("params") or {}

        try:
            result = self._run(params.get("name"), params.get("arguments") or {})
            self.channel.handle_result(
                {"type": protocol.RESULT, "requestId": request_id, "result": result}
            )
        except AppError as exc:
            self.channel.handle_result(
                {"type": protocol.RESULT, "requestId": request_id, "error": str(exc)}
            )
        except Exception as exc:
            logger.exception("Tool %s failed unexpectedly", params.get("name"))
            self.channel.handle_result(
                {"type": protocol.RESULT, "requestId": request_id, "error": str(exc)}
            )

    def _run(self, name: str | None, arguments: dict[str, Any]) -> dict[str, Any]:
        game = self.session.room.game

        if name == "login":
            char_class = arguments.get("class")
            color = arguments.get("color")
            return self._login(game, arguments["name"], char_class, color)

        return dispatch(game, self.session.player_id, name, arguments)

    def _login(
        self, game: GameService, name: str, char_class: str | None, color: str | None
    ) -> dict[str, Any]:
        current = self.session.player_id

        if current is not None and current in game.world.players:
            raise CommandError("This connection already has a character")

        result = game.login(name, char_class, color)
        self.session.adopt(result["player"]["id"])
        return result
