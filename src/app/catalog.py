from __future__ import annotations

from typing import Any

from app.colors import PLAYER_COLORS
from app.config import AppSettings
from app.entities.player import RESOURCE_KINDS
from app.fsm import ATTACKING, DEAD, IDLE, MOVING, SHOOTING, SPAWNING
from app.game import SEARCH_TYPES
from app.helpers.geometry import CARDINALS, DIRECTIONS
from app.items import ITEMS
from app.npcs.registry import ENEMIES
from app.objects import OBJECT_KINDS
from app.weapons import WEAPONS


def build_catalog(settings: AppSettings) -> dict[str, Any]:
    """The single source of truth the client reads so it never re-declares game data."""

    return {
        "weapons": {weapon_id: weapon.to_public() for weapon_id, weapon in WEAPONS.items()},
        "items": {item_id: item.to_public() for item_id, item in ITEMS.items()},
        "enemies": {
            entity: {
                "sprite": spec.sprite,
                "maxHealth": spec.max_health,
                "damage": spec.damage,
                "visionRange": spec.vision_range,
                "attackRange": spec.attack_range,
            }
            for entity, spec in ENEMIES.items()
        },
        "objects": {name: kind.to_public() for name, kind in OBJECT_KINDS.items()},
        "directions": list(DIRECTIONS),
        "cardinals": list(CARDINALS),
        "states": [IDLE, MOVING, ATTACKING, SHOOTING, SPAWNING, DEAD],
        "searchTypes": list(SEARCH_TYPES),
        "colors": list(PLAYER_COLORS),
        "resources": list(RESOURCE_KINDS),
        "limits": {
            "nameMaxLength": settings.name_max_length,
            "speechMaxLength": settings.speech_max_length,
            "spawnImmunitySeconds": settings.spawn_immunity_seconds,
            "foodHeal": settings.food_heal,
        },
    }
