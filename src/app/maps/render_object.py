from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class RenderObject:
    """A static map decoration the browser draws: sprite plus its footprint in cells."""

    sprite: str
    x: int
    y: int
    width: int
    height: int
    solid: bool

    def to_public(self) -> dict[str, Any]:
        return {
            "sprite": self.sprite,
            "x": self.x,
            "y": self.y,
            "w": self.width,
            "h": self.height,
            "solid": self.solid,
        }
