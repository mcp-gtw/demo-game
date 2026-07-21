import pytest

from app.errors import MapError
from app.maps.loader import default_map, load_tiled

TILE = 64


def _cell(x, y):
    return x * TILE, y * TILE


def _obj(name, x, y, w=1, h=1, props=None):
    ox, oy = _cell(x, y)
    obj = {"name": name, "x": ox, "y": oy, "width": w * TILE, "height": h * TILE}
    if props:
        obj["properties"] = [{"name": k, "value": v} for k, v in props.items()]
    return obj


def _valid_payload():
    ground = [11] * 16
    ground[15] = 0  # a water tile at (3, 3)
    return {
        "width": 4,
        "height": 4,
        "tilewidth": TILE,
        "tileheight": TILE,
        "tilesets": [{"firstgid": 1, "columns": 9, "tilecount": 54}],
        "layers": [
            {"type": "tilelayer", "name": "ground", "data": ground},
            {
                "type": "objectgroup",
                "name": "objects",
                "objects": [
                    _obj("building", 0, 0, 2, 2, {"sprite": "castle"}),
                    _obj("rock", 2, 0, props={"sprite": "rock1"}),
                    _obj("tree", 1, 2),
                    _obj("item", 2, 2, props={"item": "boots"}),
                ],
            },
            {
                "type": "objectgroup",
                "name": "spawns",
                "objects": [_obj("enemy_warrior", 1, 1, props={"range": 3, "max": 2})],
            },
        ],
        "properties": [
            {"name": "author", "type": "string", "value": "test"},
            {"name": "foodCap", "type": "int", "value": 5},
        ],
    }


def test_load_valid_map():
    game_map = load_tiled(_valid_payload())
    assert (game_map.cols, game_map.rows, game_map.tile_size) == (4, 4, 64)
    assert game_map.food_cap == 5
    assert game_map.tileset == {
        "image": "assets/terrain/tileset.png",
        "columns": 9,
        "tileCount": 54,
        "firstGid": 1,
    }
    assert len(game_map.ground) == 16
    assert len(game_map.render_objects) == 2
    assert len(game_map.trees) == 1
    assert [item for _, item in game_map.pickups] == ["boots"]
    assert len(game_map.spawns) == 1
    spawn = game_map.spawns[0]
    assert (spawn.entity, spawn.x, spawn.y, spawn.range, spawn.max) == ("enemy_warrior", 1, 1, 3, 2)


def test_blocked_grid_covers_water_and_footprints():
    game_map = load_tiled(_valid_payload())
    assert game_map.is_blocked(3, 3) is True  # water tile
    assert game_map.is_blocked(0, 0) is True  # 2x2 building footprint (both rows block)
    assert game_map.is_blocked(1, 1) is True  # 2x2 building footprint
    assert game_map.is_blocked(2, 0) is True  # rock
    assert game_map.is_blocked(1, 2) is False  # a tree does not block by itself
    assert game_map.is_blocked(4, 0) is True  # out of bounds
    assert game_map.in_bounds(3, 3) is True
    assert game_map.in_bounds(-1, 0) is False


def test_tall_building_caps_its_solid_rows_and_keeps_the_back_walkable():
    payload = _valid_payload()
    payload["layers"][1]["objects"] = [_obj("building", 0, 0, 2, 3, {"sprite": "castle"})]
    game_map = load_tiled(payload)
    assert game_map.is_blocked(0, 0) is False  # back row stays walkable (pass behind)
    assert game_map.is_blocked(0, 1) is True  # bottom two rows (the base) block
    assert game_map.is_blocked(0, 2) is True


def test_decoration_renders_without_blocking():
    payload = _valid_payload()
    payload["layers"][1]["objects"].append(_obj("bush", 0, 2, props={"sprite": "bush1"}))
    game_map = load_tiled(payload)
    assert any(obj.sprite == "bush1" for obj in game_map.render_objects)
    assert game_map.is_blocked(0, 2) is False


def test_public_view_shape():
    public = load_tiled(_valid_payload()).to_public()
    assert public["cols"] == 4
    assert public["tileSize"] == 64
    assert public["tileset"]["columns"] == 9
    assert len(public["ground"]) == 16
    assert public["objects"][0] == {
        "sprite": "castle",
        "x": 0,
        "y": 0,
        "w": 2,
        "h": 2,
        "solid": True,
    }
    assert public["spawns"][0] == {"entity": "enemy_warrior", "x": 1, "y": 1, "range": 3, "max": 2}


@pytest.mark.parametrize("value", [0, "x", True, None])
def test_rejects_bad_dimensions(value):
    payload = _valid_payload()
    payload["width"] = value
    with pytest.raises(MapError):
        load_tiled(payload)


@pytest.mark.parametrize("tilesets", [[], {}, None])
def test_rejects_missing_tileset(tilesets):
    payload = _valid_payload()
    payload["tilesets"] = tilesets
    with pytest.raises(MapError):
        load_tiled(payload)


def test_rejects_infinite_map():
    payload = _valid_payload()
    payload["infinite"] = True
    with pytest.raises(MapError):
        load_tiled(payload)


def test_rejects_external_tileset():
    payload = _valid_payload()
    payload["tilesets"] = [{"firstgid": 1, "source": "terrain.tsx"}]
    with pytest.raises(MapError):
        load_tiled(payload)


def test_rejects_tileset_missing_columns():
    payload = _valid_payload()
    payload["tilesets"] = [{"firstgid": 1, "tilecount": 54}]
    with pytest.raises(MapError):
        load_tiled(payload)


def test_rejects_missing_ground_layer():
    payload = _valid_payload()
    payload["layers"] = [layer for layer in payload["layers"] if layer["name"] != "ground"]
    with pytest.raises(MapError):
        load_tiled(payload)


def test_rejects_wrong_ground_length():
    payload = _valid_payload()
    payload["layers"][0]["data"] = [11] * 4
    with pytest.raises(MapError):
        load_tiled(payload)


def test_rejects_unknown_object():
    payload = _valid_payload()
    payload["layers"][1]["objects"].append(_obj("dragon", 0, 3))
    with pytest.raises(MapError):
        load_tiled(payload)


def test_rejects_missing_sprite_property():
    payload = _valid_payload()
    payload["layers"][1]["objects"] = [_obj("rock", 0, 3)]
    with pytest.raises(MapError):
        load_tiled(payload)


def test_rejects_missing_spawn_property():
    payload = _valid_payload()
    payload["layers"][2]["objects"] = [_obj("enemy_warrior", 1, 1, props={"max": 2})]
    with pytest.raises(MapError):
        load_tiled(payload)


def test_rejects_non_square_tiles():
    payload = _valid_payload()
    payload["tileheight"] = 32
    with pytest.raises(MapError):
        load_tiled(payload)


def test_rejects_object_layer_declared_as_a_tile_layer():
    payload = _valid_payload()
    payload["layers"][1]["type"] = "tilelayer"
    with pytest.raises(MapError):
        load_tiled(payload)


def test_rejects_non_numeric_food_cap():
    payload = _valid_payload()
    payload["properties"][1]["value"] = "lots"
    with pytest.raises(MapError):
        load_tiled(payload)


def test_rejects_non_numeric_spawn_property():
    payload = _valid_payload()
    payload["layers"][2]["objects"][0]["properties"] = [
        {"name": "range", "value": "near"},
        {"name": "max", "value": 2},
    ]
    with pytest.raises(MapError):
        load_tiled(payload)


def test_rejects_object_outside_bounds():
    payload = _valid_payload()
    payload["layers"][1]["objects"].append(_obj("tree", 99, 99))
    with pytest.raises(MapError):
        load_tiled(payload)


def test_map_without_object_layers_is_empty():
    payload = _valid_payload()
    payload["layers"] = [payload["layers"][0]]
    del payload["properties"]
    game_map = load_tiled(payload)
    assert game_map.render_objects == []
    assert game_map.spawns == []
    assert game_map.food_cap == 0


def test_default_map_is_consistent():
    game_map = default_map()
    assert game_map.cols > 0 and game_map.rows > 0
    assert game_map.food_cap > 0
    assert game_map.to_public()["cols"] == game_map.cols
    assert any(obj.sprite == "castle" for obj in game_map.render_objects)
