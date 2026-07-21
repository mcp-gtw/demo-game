from __future__ import annotations

import re
from typing import Any

from app.config import AppSettings
from app.entities.player import Player
from app.errors import CommandError
from app.weapons import WEAPONS
from app.world import World

_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")
_SPEECH_PATTERN = re.compile(r"^[^\r\n\t]+$")

# the entity kinds search_around understands
SEARCH_TYPES: tuple[str, ...] = ("player", "enemy", "food", "item", "coin", "tree")


class GameService:
    """Turns a session's tool calls into authoritative world operations."""

    def __init__(self, world: World, settings: AppSettings) -> None:
        self.world = world
        self.settings = settings

    def login(
        self, name: str, char_class: str | None = None, color: str | None = None
    ) -> dict[str, Any]:
        cleaned = (name or "").strip()

        if not _NAME_PATTERN.fullmatch(cleaned):
            raise CommandError("Name may only contain letters, numbers, underscores and dashes")

        if len(cleaned) > self.settings.name_max_length:
            raise CommandError(f"Name must be at most {self.settings.name_max_length} characters")

        if cleaned in self.world.players:
            raise CommandError("That name is already playing, choose another one")

        player = self.world.add_player(cleaned, cleaned, char_class, color)
        return {"player": player.to_public(self.world.time)}

    def get_player(self, player_id: str | None) -> dict[str, Any]:
        return self._player(player_id).to_public(self.world.time)

    def player_state(self, player_id: str) -> dict[str, Any] | None:
        player = self.world.players.get(player_id)
        return player.to_public(self.world.time) if player else None

    def look_around(self, player_id: str | None) -> dict[str, Any]:
        return self.world.look_around(self._player(player_id))

    def search_around(self, player_id: str | None, kind: str) -> dict[str, Any]:
        player = self._player(player_id)

        if kind not in SEARCH_TYPES:
            raise CommandError(f"Unknown search type, use one of: {', '.join(SEARCH_TYPES)}")

        return self.world.search_around(player, kind)

    def move(self, player_id: str | None, direction: str) -> dict[str, Any]:
        return self.world.move(self._player(player_id), direction)

    def attack(self, player_id: str | None, target_id: str) -> dict[str, Any]:
        return self.world.attack(self._player(player_id), target_id)

    def shoot(self, player_id: str | None, direction: str | None) -> dict[str, Any]:
        return self.world.shoot(self._player(player_id), direction)

    def chop(self, player_id: str | None, target_id: str) -> dict[str, Any]:
        return self.world.chop(self._player(player_id), target_id)

    def speak(self, player_id: str | None, text: str) -> dict[str, Any]:
        player = self._player(player_id)
        cleaned = text or ""

        if not _SPEECH_PATTERN.fullmatch(cleaned):
            raise CommandError("Speech must be a single line of text without tabs or line breaks")

        if len(cleaned) > self.settings.speech_max_length:
            limit = self.settings.speech_max_length
            raise CommandError(f"Speech must be at most {limit} characters")

        return self.world.speak(player, cleaned)

    def weapons(self, player_id: str | None) -> dict[str, Any]:
        player = self._player(player_id)
        return {"weapons": [WEAPONS[weapon_id].to_public() for weapon_id in player.weapons]}

    def _player(self, player_id: str | None) -> Player:
        if not player_id:
            raise CommandError("You are not in the game yet, call login first")

        return self.world.require_player(player_id)
