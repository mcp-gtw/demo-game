from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.helpers.geometry import Cell
from app.items import ITEMS


@dataclass(slots=True)
class Pickup:
    """A ground item a player collects by stepping onto it, changing their attributes."""

    id: str
    cell: Cell
    item: str

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": "item",
            "name": ITEMS[self.item].name,
            "item": self.item,
            "position": self.cell.as_dict(),
        }
