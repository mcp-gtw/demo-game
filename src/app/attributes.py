from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from app.config import AppSettings
from app.items import (
    ATTACK_SPEED_MULT,
    MAX_HEALTH_BONUS,
    MOVE_DURATION_MULT,
    VISION_BONUS,
    get_item,
)


@dataclass(slots=True)
class Attributes:
    """The player's live attributes, derived from base stats plus every carried item."""

    max_health: int
    move_duration: float
    vision_range: int
    attack_speed: float

    def to_public(self) -> dict[str, Any]:
        return {
            "maxHealth": self.max_health,
            "moveDuration": round(self.move_duration, 3),
            "visionRange": self.vision_range,
            "attackSpeed": round(self.attack_speed, 3),
        }


def compute_attributes(settings: AppSettings, items: Iterable[str]) -> Attributes:
    """Fold every carried item onto the base attributes to get the live attributes."""

    max_health = settings.base_max_health
    move_duration = settings.base_move_duration
    vision_range = settings.base_vision_range
    attack_speed = settings.base_attack_speed

    for item_id in items:
        spec = get_item(item_id)

        if spec is None:
            continue

        effects = spec.effects
        max_health += int(effects.get(MAX_HEALTH_BONUS, 0))
        vision_range += int(effects.get(VISION_BONUS, 0))
        move_duration *= effects.get(MOVE_DURATION_MULT, 1.0)
        attack_speed *= effects.get(ATTACK_SPEED_MULT, 1.0)

    return Attributes(
        max_health=max_health,
        move_duration=move_duration,
        vision_range=vision_range,
        attack_speed=attack_speed,
    )
