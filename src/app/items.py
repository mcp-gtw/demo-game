from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# the attribute keys an item may change
MAX_HEALTH_BONUS = "max_health_bonus"
MOVE_DURATION_MULT = "move_duration_mult"
VISION_BONUS = "vision_bonus"
ATTACK_SPEED_MULT = "attack_speed_mult"


@dataclass(frozen=True, slots=True)
class ItemSpec:
    """A collectible that permanently changes the player attributes while carried."""

    id: str
    name: str
    effects: dict[str, float] = field(default_factory=dict)

    def to_public(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "effects": dict(self.effects)}


# the item catalog: each item pulls one attribute in the player's favour
ITEMS: dict[str, ItemSpec] = {
    "heart": ItemSpec("heart", "Heart", {MAX_HEALTH_BONUS: 25}),
    "boots": ItemSpec("boots", "Swift Boots", {MOVE_DURATION_MULT: 0.85}),
    "spyglass": ItemSpec("spyglass", "Spyglass", {VISION_BONUS: 2}),
    "gauntlet": ItemSpec("gauntlet", "Gauntlet", {ATTACK_SPEED_MULT: 1.2}),
}


def get_item(item_id: str) -> ItemSpec | None:
    return ITEMS.get(item_id)
