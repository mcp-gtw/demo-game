from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.helpers.geometry import Cell


@dataclass(slots=True)
class Projectile:
    """A grid-stepped shot travelling in one direction until it hits or runs out of range."""

    id: str
    owner_id: str
    kind_name: str
    cell: Cell
    direction: str
    damage: int
    speed: int
    range_left: int
    hostile: bool = False

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": "projectile",
            "name": self.kind_name,
            "ownerId": self.owner_id,
            "hostile": self.hostile,
            "position": self.cell.as_dict(),
            "facing": self.direction,
        }
