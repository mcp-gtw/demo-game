from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from starlette.websockets import WebSocket, WebSocketDisconnect


class OAuthWebSocket(WebSocket):
    def __init__(self, websocket: WebSocket, authorized: Callable[[], Awaitable[bool]]) -> None:
        super().__init__(websocket.scope, websocket.receive, websocket.send)
        self.authorized = authorized

    async def send_json(self, data: Any, mode: str = "text") -> None:
        if not await self.authorized():
            await self.close(code=1008)
            raise WebSocketDisconnect(code=1008)

        await super().send_json(data, mode)
