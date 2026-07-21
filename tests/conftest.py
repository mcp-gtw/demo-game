import random

import pytest

from app.config import AppSettings
from app.entities.enemy import Enemy
from app.helpers.geometry import Cell
from app.maps.map_definition import MapDefinition
from app.maps.spawn_point import SpawnPoint
from app.npcs.behavior import Behavior
from app.world import World

_TILESET = {"image": "assets/terrain/tileset.png", "columns": 9, "tileCount": 54, "firstGid": 1}


def make_enemy(**overrides):
    """Build an Enemy with sane aggressive-warrior defaults, overriding only what a test needs."""

    params = dict(
        id="foe",
        entity="enemy_warrior",
        cell=Cell(0, 0),
        max_health=60,
        spawn_index=0,
        damage=12,
        vision_range=6,
        attack_range=1,
        speed_duration=0.5,
        attack_cooldown=1.0,
        attack_duration=0.4,
        respawn_seconds=6.0,
        behavior=Behavior.AGGRESSIVE,
        ranged=False,
        projectile_speed=0,
        flee_range=0,
        flee_when_attacked=False,
        spook_seconds=0.0,
        wander_chance=0.35,
    )
    params.update(overrides)
    return Enemy(**params)


def make_map(
    cols=20,
    rows=20,
    blocked=(),
    render_objects=(),
    trees=(),
    pickups=(),
    spawns=(),
    food_cap=0,
):
    """Build a MapDefinition of solid grass with the given blocked cells and objects."""

    ground = [11] * (cols * rows)

    for x, y in blocked:
        ground[y * cols + x] = 0

    return MapDefinition(
        cols=cols,
        rows=rows,
        tile_size=64,
        ground=ground,
        tileset=dict(_TILESET),
        render_objects=list(render_objects),
        trees=[Cell(x, y) for x, y in trees],
        pickups=[(Cell(x, y), item) for x, y, item in pickups],
        spawns=list(spawns),
        blocked=frozenset(blocked),
        food_cap=food_cap,
    )


@pytest.fixture
def settings():
    return AppSettings()


@pytest.fixture
def bare_map():
    # a small open map with one solid wall column and no NPC spawns for precise placement
    wall = [(10, y) for y in range(20)]
    return make_map(blocked=wall, food_cap=3)


@pytest.fixture
def world(settings, bare_map):
    return World(settings, bare_map, rng=random.Random(7))


@pytest.fixture
def spawn_map():
    return make_map(spawns=[SpawnPoint(entity="enemy_warrior", x=10, y=10, range=2, max=2)])
