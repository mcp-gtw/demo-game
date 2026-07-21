from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.attributes import Attributes
from app.fsm import StateMachine
from app.helpers.geometry import Cell
from app.weapons import WEAPONS

# the resources a player accumulates, the single source the catalog and world share
RESOURCE_KINDS = ("wood", "gold")


@dataclass(slots=True)
class Player:
    """A logged-in player. Everything the world knows about an agent lives here."""

    id: str
    name: str
    cell: Cell
    attributes: Attributes
    char_class: str
    sprite: str
    color: str
    facing: str = "down"
    health: int = 0
    kills: int = 0
    deaths: int = 0
    alive: bool = True
    items: list[str] = field(default_factory=list)
    weapons: list[str] = field(default_factory=list)
    resources: dict[str, int] = field(default_factory=lambda: dict.fromkeys(RESOURCE_KINDS, 0))
    machine: StateMachine = field(default_factory=StateMachine)
    busy_until: float = 0.0
    attack_ready_at: float = 0.0
    immune_until: float = 0.0
    respawn_at: float | None = None
    vision_pulse_seq: int = 0
    speech_text: str | None = None
    speech_until: float = 0.0

    def __post_init__(self) -> None:
        if self.health == 0:
            self.health = self.attributes.max_health

    @property
    def state(self) -> str:
        return self.machine.state

    def is_immune(self, now: float) -> bool:
        return now < self.immune_until

    def weapon_of(self, kind: str) -> str | None:
        for weapon_id in self.weapons:
            if WEAPONS[weapon_id].kind == kind:
                return weapon_id

        return None

    def to_public(self, now: float) -> dict[str, Any]:
        """The full private view the owning agent receives, with everything it may know."""

        return {
            **self._common(now),
            "class": self.char_class,
            "color": self.color,
            "kills": self.kills,
            "deaths": self.deaths,
            "items": list(self.items),
            "weapons": [WEAPONS[weapon_id].to_public() for weapon_id in self.weapons],
            "attributes": self.attributes.to_public(),
            "visionRange": self.attributes.vision_range,
            "resources": dict(self.resources),
        }

    def to_view(self, now: float) -> dict[str, Any]:
        """The public view other agents receive through tools, hiding private items and vision."""

        return {**self._common(now), "kills": self.kills, "deaths": self.deaths}

    def to_snapshot(self, now: float) -> dict[str, Any]:
        """The render view streamed to browsers, adding the vision range and resources."""

        return {
            **self.to_view(now),
            "sprite": self.sprite,
            "color": self.color,
            "moveMs": round(self.attributes.move_duration * 1000),
            "visionRange": self.attributes.vision_range,
            "resources": dict(self.resources),
        }

    def _common(self, now: float) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": "player",
            "name": self.name,
            "position": self.cell.as_dict(),
            "facing": self.facing,
            "state": self.state,
            "health": self.health,
            "maxHealth": self.attributes.max_health,
            "alive": self.alive,
            "immune": self.is_immune(now),
            "visionPulseSeq": self.vision_pulse_seq,
            "speech": self.speech_text if now < self.speech_until else None,
        }
