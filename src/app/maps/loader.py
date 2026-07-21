from __future__ import annotations

import json
from itertools import product
from pathlib import Path
from typing import Any

from app.errors import MapError
from app.helpers.geometry import Cell
from app.maps.map_definition import MapDefinition
from app.maps.render_object import RenderObject
from app.maps.spawn_point import SpawnPoint
from app.objects import get_object_kind

_MAP_PATH = Path(__file__).parent.parent / "web" / "assets" / "map" / "island.tmj"

# the client serves the tileset from the web root, while the .tmj stores the image relative to the
# map file so Tiled resolves it, so the client path is fixed here rather than read from the map
_TILESET_IMAGE = "assets/terrain/tileset.png"

# a solid blocks at most its bottom two footprint rows (its base), so a taller building keeps its
# back rows walkable and an actor can pass behind it
SOLID_DEPTH = 2


def load_tiled(data: dict[str, Any]) -> MapDefinition:
    """Turn a Tiled orthogonal map (.tmj) into a MapDefinition, rejecting anything malformed."""

    if data.get("infinite"):
        raise MapError("Infinite maps are not supported, author a fixed-size map")

    cols = _positive_int(data, "width")
    rows = _positive_int(data, "height")
    tile = _positive_int(data, "tilewidth")

    if _positive_int(data, "tileheight") != tile:
        raise MapError("The map must use square tiles, so tilewidth must equal tileheight")

    tilesets = data.get("tilesets")

    if not isinstance(tilesets, list) or not tilesets:
        raise MapError("The map must declare a tileset")

    source = tilesets[0]

    if "source" in source:
        raise MapError("The tileset must be embedded in the map, not an external .tsx file")

    tileset = {
        "image": _TILESET_IMAGE,
        "columns": _positive_int(source, "columns"),
        "tileCount": _positive_int(source, "tilecount"),
        "firstGid": _positive_int(source, "firstgid"),
    }

    layers = {layer["name"]: layer for layer in data.get("layers", [])}
    ground = layers["ground"].get("data") if "ground" in layers else None

    if not isinstance(ground, list) or len(ground) != cols * rows:
        raise MapError("The map must have a 'ground' tile layer matching its size")

    blocked = {(index % cols, index // cols) for index, gid in enumerate(ground) if gid == 0}
    render_objects: list[RenderObject] = []
    trees: list[Cell] = []
    pickups: list[tuple[Cell, str]] = []

    for obj in _objects(layers, "objects"):
        cell_x, cell_y = _object_cell(obj, tile, cols, rows)
        width = max(1, _as_int(obj, "width") // tile)
        height = max(1, _as_int(obj, "height") // tile)
        kind = get_object_kind(obj["name"])

        if kind.choppable:
            trees.append(Cell(cell_x, cell_y))
        elif kind.collectible:
            pickups.append((Cell(cell_x, cell_y), _prop(obj, "item")))
        else:
            render_objects.append(
                RenderObject(_prop(obj, "sprite"), cell_x, cell_y, width, height, kind.solid)
            )

            if kind.solid:
                # only the bottom rows (the base) block, capped at SOLID_DEPTH, so a taller building
                # leaves its back rows walkable and an actor can pass behind it for a sense of depth
                front = cell_y + height - min(height, SOLID_DEPTH)
                cols_range = range(cell_x, cell_x + width)
                blocked.update(product(cols_range, range(front, cell_y + height)))

    spawns = [
        SpawnPoint(
            entity=obj["name"],
            x=_as_int(obj, "x") // tile,
            y=_as_int(obj, "y") // tile,
            range=_coerce_int(_prop(obj, "range"), f"spawn '{obj['name']}' range"),
            max=_coerce_int(_prop(obj, "max"), f"spawn '{obj['name']}' max"),
        )
        for obj in _objects(layers, "spawns")
    ]

    return MapDefinition(
        cols=cols,
        rows=rows,
        tile_size=tile,
        ground=ground,
        tileset=tileset,
        render_objects=render_objects,
        trees=trees,
        pickups=pickups,
        spawns=spawns,
        blocked=frozenset(blocked),
        food_cap=_map_prop(data, "foodCap", 0),
    )


def default_map() -> MapDefinition:
    return load_tiled(json.loads(_MAP_PATH.read_text(encoding="utf-8")))


def _objects(layers: dict[str, Any], name: str) -> list[dict[str, Any]]:
    layer = layers.get(name)

    if layer is None:
        return []

    if layer.get("type") != "objectgroup" or not isinstance(layer.get("objects"), list):
        raise MapError(f"Layer '{name}' must be an object group")

    return layer["objects"]


def _object_cell(obj: dict[str, Any], tile: int, cols: int, rows: int) -> tuple[int, int]:
    x = _as_int(obj, "x") // tile
    y = _as_int(obj, "y") // tile

    if not (0 <= x < cols and 0 <= y < rows):
        raise MapError(f"Object '{obj['name']}' lies outside the map bounds")

    return x, y


def _prop(obj: dict[str, Any], name: str) -> Any:
    for entry in obj.get("properties", []):
        if entry["name"] == name:
            return entry["value"]

    raise MapError(f"Object '{obj['name']}' is missing the '{name}' property")


def _map_prop(data: dict[str, Any], name: str, default: int) -> int:
    for entry in data.get("properties", []):
        if entry["name"] == name:
            return _coerce_int(entry["value"], f"map property '{name}'")

    return default


def _positive_int(data: dict[str, Any], key: str) -> int:
    value = data.get(key)

    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise MapError(f"'{key}' must be a positive integer")

    return value


def _as_int(source: dict[str, Any], key: str) -> int:
    return _coerce_int(source.get(key), f"'{key}'")


def _coerce_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MapError(f"{label} must be a number")

    return int(value)
