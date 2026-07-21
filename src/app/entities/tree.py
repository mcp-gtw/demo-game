from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.helpers.geometry import Cell


@dataclass(slots=True)
class Tree:
    """A breakable obstacle. It blocks movement until chopped down, then regrows."""

    id: str
    cell: Cell
    max_hits: int = 3
    hits: int = 3
    broken: bool = False
    regrow_at: float | None = None

    @property
    def solid(self) -> bool:
        return not self.broken

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": "tree",
            "name": "tree",
            "position": self.cell.as_dict(),
            "broken": self.broken,
            "hits": self.hits,
            "maxHits": self.max_hits,
        }
