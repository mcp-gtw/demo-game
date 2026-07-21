import asyncio
import dataclasses

import pytest
from conftest import make_enemy

from app.attributes import compute_attributes
from app.config import AppSettings
from app.entities.player import Player
from app.entities.projectile import Projectile
from app.errors import MapError
from app.helpers.geometry import Cell
from app.npcs.loot_drop import LootDrop
from app.npcs.registry import ENEMIES, _validate_loot, get_enemy_spec
from app.stream import StreamHub


def test_unknown_enemy_spec_raises():
    with pytest.raises(MapError):
        get_enemy_spec("dragon")


def test_registry_rejects_an_unknown_loot_resource():
    spec = dataclasses.replace(ENEMIES["enemy_warrior"], loot=(LootDrop("silver", 1, 1.0),))
    with pytest.raises(MapError):
        _validate_loot({"bad": spec})


def test_entities_keep_explicit_health():
    enemy = make_enemy(
        id="e",
        entity="x",
        max_health=10,
        damage=1,
        vision_range=1,
        speed_duration=0.1,
        attack_cooldown=0.1,
        health=5,
    )
    assert enemy.health == 5

    player = Player(
        id="p",
        name="p",
        cell=Cell(0, 0),
        attributes=compute_attributes(AppSettings(), []),
        char_class="warrior",
        sprite="warrior",
        color="blue",
        health=7,
    )
    assert player.health == 7


def test_projectile_public_view():
    public = Projectile("s", "o", "arrow", Cell(1, 2), "up", 5, 2, 7).to_public()
    assert public["kind"] == "projectile"
    assert public["facing"] == "up"


def test_player_views_hide_and_reveal():
    player = Player(
        id="p",
        name="p",
        cell=Cell(0, 0),
        attributes=compute_attributes(AppSettings(), []),
        char_class="warrior",
        sprite="warrior",
        color="blue",
    )
    assert "visionRange" in player.to_snapshot(0.0)
    assert "items" not in player.to_view(0.0)
    assert "items" in player.to_public(0.0)


def test_player_views_expose_resources():
    player = Player(
        id="p",
        name="p",
        cell=Cell(0, 0),
        attributes=compute_attributes(AppSettings(), []),
        char_class="warrior",
        sprite="warrior",
        color="blue",
    )
    player.resources["wood"] = 2
    assert player.to_public(0.0)["resources"] == {"wood": 2, "gold": 0}
    assert player.to_snapshot(0.0)["resources"] == {"wood": 2, "gold": 0}
    assert "resources" not in player.to_view(0.0)


async def test_stream_hub_delivers_and_drops_stuck_clients():
    hub = StreamHub(send_timeout=0.05)

    await hub.broadcast({"a": 0})

    good_sent = []

    class Good:
        async def send_json(self, data):
            good_sent.append(data)

    class Raises:
        async def send_json(self, data):
            raise RuntimeError("gone")

    class Stuck:
        async def send_json(self, data):
            await asyncio.sleep(1)

    good = Good()

    for client in (good, Raises(), Stuck()):
        hub.subscribe(client)

    await hub.broadcast({"a": 1})
    assert good_sent == [{"a": 1}]

    await hub.broadcast({"a": 2})
    assert good_sent == [{"a": 1}, {"a": 2}]
