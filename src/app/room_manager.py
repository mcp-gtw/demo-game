from __future__ import annotations

from app.config import AppSettings
from app.maps.map_definition import MapDefinition
from app.room import Room

DEFAULT_ROOM_ID = "world"


class RoomManager:
    """Holds every game room and guarantees a default room exists from startup."""

    def __init__(self, settings: AppSettings) -> None:
        self.settings = settings
        self.rooms: dict[str, Room] = {DEFAULT_ROOM_ID: Room(DEFAULT_ROOM_ID, settings)}

    @property
    def default(self) -> Room:
        return self.rooms[DEFAULT_ROOM_ID]

    def create(self, room_id: str, game_map: MapDefinition | None = None) -> Room:
        room = Room(room_id, self.settings, game_map)
        self.rooms[room_id] = room
        return room

    def all(self) -> list[Room]:
        return list(self.rooms.values())
