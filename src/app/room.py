from __future__ import annotations

from app.config import AppSettings
from app.game import GameService
from app.maps.map_definition import MapDefinition
from app.stream import StreamHub
from app.world import World


class Room:
    """One isolated game world with its own players, simulation and render subscribers."""

    def __init__(
        self, room_id: str, settings: AppSettings, game_map: MapDefinition | None = None
    ) -> None:
        self.id = room_id
        self.world = World(settings, game_map)
        self.game = GameService(self.world, settings)
        self.hub = StreamHub(settings.stream_send_timeout_seconds)
