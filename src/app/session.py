from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

from app.room import Room


@dataclass(slots=True)
class Session:
    """One game session: its private channel, the room it plays in and its adopted player."""

    channel_id: str
    mcp_token: str
    room: Room
    auth_method: str = "token"
    oauth_authorized_until: int = 0
    logged_in: asyncio.Event = field(default_factory=asyncio.Event)
    player_id: str | None = None
    connections: int = 0
    last_mcp_activity: float | None = None
    teardown: asyncio.Task[None] | None = None

    def touch(self) -> None:
        self.last_mcp_activity = time.monotonic()

    def adopt(self, player_id: str) -> None:
        self.player_id = player_id
        self.logged_in.set()
