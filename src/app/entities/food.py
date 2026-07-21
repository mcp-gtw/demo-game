from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.helpers.geometry import Cell


@dataclass(slots=True)
class Food:
    """A collectible that restores health when a player steps onto it."""

    id: str
    cell: Cell
    heal: int

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": "food",
            "name": "meat",
            "position": self.cell.as_dict(),
        }
