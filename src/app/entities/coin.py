from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.helpers.geometry import Cell


@dataclass(slots=True)
class Coin:
    """A gold coin lying on the ground. Stepping onto it adds its value to the player's gold."""

    id: str
    cell: Cell
    value: int

    def to_public(self) -> dict[str, Any]:
        return {"id": self.id, "kind": "coin", "position": self.cell.as_dict(), "value": self.value}
