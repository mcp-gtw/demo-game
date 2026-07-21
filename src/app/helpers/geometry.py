from __future__ import annotations

import math
from dataclasses import dataclass

# eight movement directions as integer cell deltas
DIRECTIONS: dict[str, tuple[int, int]] = {
    "up": (0, -1),
    "down": (0, 1),
    "left": (-1, 0),
    "right": (1, 0),
    "up_left": (-1, -1),
    "up_right": (1, -1),
    "down_left": (-1, 1),
    "down_right": (1, 1),
}

# the four cardinal directions a directional scan reports separately
CARDINALS: tuple[str, ...] = ("up", "down", "left", "right")


@dataclass(slots=True)
class Cell:
    """An integer grid position. The server reasons only in cells, never in pixels."""

    x: int
    y: int

    def copy(self) -> Cell:
        return Cell(self.x, self.y)

    def moved(self, dx: int, dy: int) -> Cell:
        return Cell(self.x + dx, self.y + dy)

    def stepped(self, direction: str) -> Cell:
        dx, dy = DIRECTIONS[direction]
        return Cell(self.x + dx, self.y + dy)

    def distance_to(self, other: Cell) -> float:
        return math.hypot(self.x - other.x, self.y - other.y)

    def chebyshev_to(self, other: Cell) -> int:
        return max(abs(self.x - other.x), abs(self.y - other.y))

    def equals(self, other: Cell) -> bool:
        return self.x == other.x and self.y == other.y

    def as_dict(self) -> dict[str, int]:
        return {"x": self.x, "y": self.y}
