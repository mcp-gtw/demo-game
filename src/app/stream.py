from __future__ import annotations

import asyncio
import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class StreamClient(Protocol):
    async def send_json(self, data: Any) -> None: ...


class StreamHub:
    """Fans out world snapshots to every connected render client."""

    def __init__(self, send_timeout: float) -> None:
        self._subscribers: set[StreamClient] = set()
        self._send_timeout = send_timeout

    def subscribe(self, client: StreamClient) -> None:
        self._subscribers.add(client)

    def unsubscribe(self, client: StreamClient) -> None:
        self._subscribers.discard(client)

    async def broadcast(self, message: dict[str, Any]) -> None:
        subscribers = list(self._subscribers)

        if not subscribers:
            return

        # deliver concurrently and time-bounded so one stuck consumer never stalls the others
        unreachable = await asyncio.gather(*(self._deliver(c, message) for c in subscribers))

        for client in unreachable:
            if client is not None:
                self._subscribers.discard(client)

    async def _deliver(self, client: StreamClient, message: dict[str, Any]) -> StreamClient | None:
        try:
            await asyncio.wait_for(client.send_json(message), self._send_timeout)
            return None
        except Exception:
            logger.debug("Dropping unreachable stream client", exc_info=True)
            return client
