import random

import pytest
from conftest import make_enemy, make_map
from test_world import make_ready, place_enemy

from app.entities.coin import Coin
from app.entities.food import Food
from app.entities.pickup import Pickup
from app.entities.projectile import Projectile
from app.entities.tree import Tree
from app.errors import CommandError
from app.helpers.geometry import Cell
from app.maps.spawn_point import SpawnPoint
from app.world import World


def test_dead_player_cannot_act(world):
    player = make_ready(world.add_player("neo", "neo"), 5, 5)
    player.weapons = ["sword", "bow"]
    player.alive = False
    player.machine.state = "dead"
    assert world.move(player, "right")["reason"] == "dead"
    assert world.attack(player, "x")["reason"] == "dead"
    assert world.shoot(player, "right")["reason"] == "dead"
    assert world.chop(player, "t")["reason"] == "dead"


def test_dead_player_cannot_observe_or_speak(world):
    player = make_ready(world.add_player("neo", "neo"), 5, 5)
    player.alive = False
    player.machine.state = "dead"
    seq = player.vision_pulse_seq
    assert world.look_around(player) == {"reason": "dead", "visible": [], "directions": {}}
    assert player.vision_pulse_seq == seq  # a corpse never pulses a vision wave
    assert world.search_around(player, "enemy")["reason"] == "dead"
    assert world.speak(player, "boo")["said"] is None
    assert player.speech_text is None


def test_damage_ignores_an_already_dead_target(world):
    enemy = place_enemy(world, 6, 5, health=5)
    assert world._damage(enemy, 99, attacker=None) is True
    assert not enemy.alive
    deaths_marker = enemy.respawn_at

    # a second hit on the corpse must not kill again or reset the respawn timer
    assert world._damage(enemy, 99, attacker=None) is False
    assert enemy.respawn_at == deaths_marker


def test_shoot_on_cooldown_branch(world):
    player = make_ready(world.add_player("neo", "neo"), 5, 5)
    player.weapons = ["sword", "bow"]
    player.attack_ready_at = world.time + 10
    assert world.shoot(player, "right")["reason"] == "on_cooldown"


def test_bad_directions_raise(world):
    player = make_ready(world.add_player("neo", "neo"), 5, 5)
    player.weapons = ["sword", "bow"]
    with pytest.raises(CommandError):
        world.move(player, "north")
    with pytest.raises(CommandError):
        world.shoot(player, "north")


def test_projectile_flies_out_of_bounds(world):
    player = make_ready(world.add_player("neo", "neo"), 1, 5)
    player.weapons = ["sword", "bow"]
    world.shoot(player, "left")
    for _ in range(3):
        world.tick(0.1)
    assert not world.projectiles


def test_projectile_stopped_by_tree(world):
    player = make_ready(world.add_player("neo", "neo"), 3, 5)
    player.weapons = ["sword", "bow"]
    world.trees["t"] = Tree("t", Cell(5, 5))
    world.shoot(player, "right")
    for _ in range(3):
        world.tick(0.1)
    assert not world.projectiles


def test_attack_player_target(world):
    attacker = make_ready(world.add_player("a", "a"), 5, 5)
    target = make_ready(world.add_player("b", "b"), 6, 5)
    target.immune_until = 0.0
    result = world.attack(attacker, "b")
    assert result["targetKind"] == "player"


def test_attack_immune_target_is_invalid(world):
    attacker = make_ready(world.add_player("a", "a"), 5, 5)
    target = make_ready(world.add_player("b", "b"), 6, 5)
    target.immune_until = world.time + 5
    assert world.attack(attacker, "b")["reason"] == "invalid_target"


def test_visible_includes_every_kind(world):
    player = make_ready(world.add_player("neo", "neo"), 5, 5)
    make_ready(world.add_player("b", "b"), 6, 5)
    world.food["f"] = Food("f", Cell(5, 6), 10)
    world.pickups["pk"] = Pickup("pk", Cell(4, 5), "boots")
    kinds = {entry["kind"] for entry in world.look_around(player)["visible"]}
    assert {"player", "food", "item"} <= kinds


def test_scan_reports_player_and_clear(world):
    player = make_ready(world.add_player("neo", "neo"), 5, 5)
    make_ready(world.add_player("b", "b"), 7, 5)
    directions = world.look_around(player)["directions"]
    assert directions["right"]["type"] == "player"
    assert directions["down"]["type"] == "clear"


def test_facing_towards_same_cell_defaults_down(world):
    assert world._facing_towards(Cell(3, 3), Cell(3, 3)) == "down"


def test_occupied_by_actor_helper(world):
    first = place_enemy(world, 5, 5)
    second = make_enemy(id="foe2", cell=Cell(6, 5))
    world.enemies["foe2"] = second
    assert world._occupied_by_actor(Cell(6, 5), first) is True


def test_move_is_blocked_by_another_actor_but_can_leave_a_shared_cell(world):
    a = make_ready(world.add_player("a", "a"), 5, 5)
    b = make_ready(world.add_player("b", "b"), 6, 5)

    assert world.move(a, "right")["reason"] == "blocked"  # cannot step onto b

    b.cell = Cell(5, 5)  # now stacked with a
    result = world.move(a, "down")  # can still leave to an empty cell
    assert result["moved"] is True
    assert a.cell.as_dict() == {"x": 5, "y": 6}


def test_enemy_melee_does_not_hurt_an_immune_player(world):
    enemy = place_enemy(world, 5, 5)
    prey = make_ready(world.add_player("neo", "neo"), 5, 6)
    prey.immune_until = world.time + 5
    world._enemy_attack(enemy, prey)
    assert prey.health == prey.attributes.max_health


def _archer_world(settings):
    game_map = make_map(spawns=[SpawnPoint("enemy_archer", 10, 5, 0, 1)])
    world = World(settings, game_map, rng=random.Random(1))
    return world, next(iter(world.enemies.values()))


def test_archer_spawns_ranged_and_fires_when_aligned(settings):
    world, archer = _archer_world(settings)
    assert archer.ranged is True
    assert archer.projectile_speed == 2
    archer.cell = Cell(10, 5)
    player = make_ready(world.add_player("neo", "neo"), 14, 5)
    player.immune_until = 0.0

    world._advance_enemies()
    assert archer.state == "shooting"
    assert next(iter(world.projectiles.values())).hostile is True

    world._advance_enemies()  # still on cooldown, no second arrow
    assert len(world.projectiles) == 1

    for _ in range(4):
        world.tick(0.1)
    assert player.health < player.attributes.max_health


def test_archer_repositions_instead_of_wasting_an_off_axis_shot(settings):
    world, archer = _archer_world(settings)
    archer.cell = Cell(10, 5)
    player = make_ready(world.add_player("neo", "neo"), 12, 6)  # in range but off any ray
    player.immune_until = 0.0

    before = archer.cell.copy()
    world._advance_enemies()
    assert world.projectiles == {}
    assert not archer.cell.equals(before)


def test_enemy_arrow_passes_through_other_enemies(settings):
    world, archer = _archer_world(settings)
    archer.cell = Cell(10, 5)
    archer.attack_ready_at = 0.0
    bystander = place_enemy(world, 12, 5, health=40)
    player = make_ready(world.add_player("neo", "neo"), 14, 5)
    player.immune_until = 0.0

    world._advance_enemies()
    for _ in range(4):
        world.tick(0.1)

    assert player.health < player.attributes.max_health
    assert bystander.health == 40


def test_enemy_blocked_step(settings):
    wall = [(6, y) for y in range(20)]
    game_map = make_map(blocked=wall, spawns=[SpawnPoint("enemy_warrior", 5, 10, 0, 1)])
    world = World(settings, game_map, rng=random.Random(1))
    player = make_ready(world.add_player("neo", "neo"), 8, 10)
    player.immune_until = 0.0
    for _ in range(10):
        world.tick(0.2)
    assert all(enemy.cell.x < 6 for enemy in world.enemies.values())


def test_enemy_revives_after_delay(settings, spawn_map):
    world = World(settings, spawn_map, rng=random.Random(3))
    enemy = next(iter(world.enemies.values()))
    world._kill(enemy)
    assert not enemy.alive
    world.time = enemy.respawn_at
    world._resolve_respawns()
    assert enemy.alive


def test_dead_player_cannot_chop(world):
    player = make_ready(world.add_player("neo", "neo"), 5, 5)
    world.trees["t"] = Tree("t", Cell(6, 5))
    player.alive = False
    assert world.chop(player, "t")["reason"] == "dead"


def test_tree_regrows(world):
    tree = Tree("t", Cell(5, 5), max_hits=1, hits=1)
    world.trees["t"] = tree
    player = make_ready(world.add_player("neo", "neo"), 5, 4)
    world.chop(player, "t")
    assert tree.broken
    world.time = tree.regrow_at
    world._regrow_trees()
    assert not tree.broken


def test_tree_waits_to_regrow_under_a_standing_actor(world):
    tree = Tree("t", Cell(5, 5), max_hits=1, hits=1, broken=True, regrow_at=1.0)
    world.trees["t"] = tree
    stander = make_ready(world.add_player("neo", "neo"), 5, 5)
    world.time = 2.0

    world._regrow_trees()
    assert tree.broken  # still broken, the actor blocks the regrowth

    stander.cell = Cell(6, 5)
    world._regrow_trees()
    assert not tree.broken


def test_item_preserves_health_ratio(world):
    player = make_ready(world.add_player("neo", "neo"), 5, 5)
    player.health = 50
    world.pickups["pk"] = Pickup("pk", Cell(6, 5), "heart")
    world.move(player, "right")
    assert "heart" in player.items
    assert player.attributes.max_health == 125
    assert player.health > 50


def test_pickup_replenish_respects_cap_and_timing(world):
    world._next_pickup_at = 0.0
    world._replenish_pickups()
    assert len(world.pickups) == 1

    for index in range(world.settings.pickup_cap):
        world.pickups[f"x{index}"] = Pickup(f"x{index}", Cell(index, 15), "boots")
    world._next_pickup_at = 0.0
    world._replenish_pickups()
    assert len(world.pickups) == world.settings.pickup_cap + 1

    world.pickups.clear()
    world._next_pickup_at = world.time + 100
    world._replenish_pickups()
    assert len(world.pickups) == 0


def test_coin_replenish_respects_cap_and_timing(world):
    world._next_coin_at = 0.0
    world._replenish_coins()
    assert len(world.coins) == 1

    for index in range(world.settings.coin_cap):
        world.coins[f"c{index}"] = Coin(f"c{index}", Cell(index, 15), 1)
    world._next_coin_at = 0.0
    world._replenish_coins()
    assert len(world.coins) == world.settings.coin_cap + 1

    world.coins.clear()
    world._next_coin_at = world.time + 100
    world._replenish_coins()
    assert len(world.coins) == 0


def test_coin_replenish_skips_when_no_free_cell(settings):
    blocked = [(x, y) for x in range(4) for y in range(4)]
    world = World(settings, make_map(cols=4, rows=4, blocked=blocked), rng=random.Random(1))
    world._next_coin_at = 0.0
    world._replenish_coins()
    assert len(world.coins) == 0


def test_pickup_replenish_skips_when_no_free_cell(settings):
    blocked = [(x, y) for x in range(4) for y in range(4)]
    world = World(settings, make_map(cols=4, rows=4, blocked=blocked), rng=random.Random(1))
    world._next_pickup_at = 0.0
    world._replenish_pickups()
    assert world.pickups == {}


def test_food_replenish_respects_cap_and_timing(world):
    for index in range(world.map.food_cap):
        world.food[f"x{index}"] = Food(f"x{index}", Cell(index, 0), 10)
    world._next_food_at = 0.0
    world._replenish_food()
    assert len(world.food) == world.map.food_cap

    world.food.clear()
    world._next_food_at = world.time + 100
    world._replenish_food()
    assert len(world.food) == 0


def test_player_id_is_the_name_and_distinct_from_enemy_ids(settings, spawn_map):
    from app.game import GameService

    world = World(settings, spawn_map, rng=random.Random(1))
    result = GameService(world, settings).login("hero")
    assert result["player"]["id"] == "hero"
    assert "hero" in world.players
    assert all(":" in enemy_id for enemy_id in world.enemies)


def test_snapshot_includes_every_group(world):
    make_ready(world.add_player("neo", "neo"), 5, 5)
    world.food["f"] = Food("f", Cell(1, 1), 10)
    world.pickups["pk"] = Pickup("pk", Cell(2, 2), "boots")
    world.trees["t"] = Tree("t", Cell(3, 3))
    world.projectiles["s"] = Projectile("s", "neo", "arrow", Cell(4, 4), "right", 5, 2, 7)
    snapshot = world.snapshot()
    assert snapshot["players"] and snapshot["food"] and snapshot["pickups"]
    assert snapshot["trees"] and snapshot["projectiles"]


def test_defeating_an_enemy_drops_its_loot(world):
    from app.npcs.registry import get_enemy_spec

    player = make_ready(world.add_player("neo", "neo"), 5, 5)
    enemy = place_enemy(world, 6, 5, health=1)
    world.attack(player, "foe")
    gold = next(
        drop.amount for drop in get_enemy_spec("enemy_warrior").loot if drop.resource == "gold"
    )
    assert any(c.value == gold and c.cell.equals(enemy.cell) for c in world.coins.values())


def test_defeating_a_player_awards_no_gold(world):
    attacker = make_ready(world.add_player("a", "a"), 5, 5)
    victim = make_ready(world.add_player("b", "b"), 6, 5)
    victim.health = 1
    world.attack(attacker, "b")
    assert not victim.alive
    assert attacker.kills == 1
    assert attacker.resources["gold"] == 0


def test_look_around_reports_offset_and_direction(world):
    player = make_ready(world.add_player("neo", "neo"), 5, 5)
    place_enemy(world, 7, 5)
    entry = next(e for e in world.look_around(player)["visible"] if e["kind"] == "enemy")
    assert entry["offset"] == {"dx": 2, "dy": 0}
    assert entry["direction"] == "right"
    assert entry["steps"] == 2


def test_chop_without_a_melee_weapon(world):
    player = make_ready(world.add_player("neo", "neo"), 5, 5)
    player.weapons = []
    world.trees["t"] = Tree("t", Cell(6, 5))
    assert world.chop(player, "t")["reason"] == "no_melee_weapon"


def test_chop_enters_the_attacking_state(world):
    player = make_ready(world.add_player("neo", "neo"), 5, 5)
    world.trees["t"] = Tree("t", Cell(6, 5))
    world.chop(player, "t")
    assert player.machine.state == "attacking"
    assert player.busy_until > world.time


def test_look_around_marks_own_cell_as_here(world):
    player = make_ready(world.add_player("neo", "neo"), 5, 5)
    world.food["f"] = Food("f", Cell(5, 5), 10)
    entry = next(e for e in world.look_around(player)["visible"] if e["kind"] == "food")
    assert entry["direction"] == "here"
    assert entry["offset"] == {"dx": 0, "dy": 0}
    assert entry["steps"] == 0
