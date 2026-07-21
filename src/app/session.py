from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from app.room import Room


@dataclass(slots=True)
class Session:
    """One browser session: its private channel, the room it plays in and its adopted player."""

    channel_id: str
    mcp_token: str
    room: Room
    logged_in: asyncio.Event = field(default_factory=asyncio.Event)
    player_id: str | None = None
    connections: int = 0
    teardown: asyncio.Task[None] | None = None

    def adopt(self, player_id: str) -> None:
        self.player_id = player_id
        self.logged_in.set()
