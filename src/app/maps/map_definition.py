from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.helpers.geometry import Cell
from app.maps.render_object import RenderObject
from app.maps.spawn_point import SpawnPoint


@dataclass(slots=True)
class MapDefinition:
    """A validated Tiled map: the ground tiles, its objects and the walkability grid."""

    cols: int
    rows: int
    tile_size: int
    ground: list[int]
    tileset: dict[str, Any]
    render_objects: list[RenderObject]
    trees: list[Cell]
    pickups: list[tuple[Cell, str]]
    spawns: list[SpawnPoint]
    blocked: frozenset[tuple[int, int]]
    food_cap: int

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.cols and 0 <= y < self.rows

    def is_blocked(self, x: int, y: int) -> bool:
        return not self.in_bounds(x, y) or (x, y) in self.blocked

    def to_public(self) -> dict[str, Any]:
        return {
            "cols": self.cols,
            "rows": self.rows,
            "tileSize": self.tile_size,
            "tileset": self.tileset,
            "ground": self.ground,
            "objects": [obj.to_public() for obj in self.render_objects],
            "spawns": [
                {"entity": s.entity, "x": s.x, "y": s.y, "range": s.range, "max": s.max}
                for s in self.spawns
            ],
        }
