import random

import pytest
from conftest import make_enemy, make_map

from app.config import AppSettings
from app.entities.coin import Coin
from app.entities.food import Food
from app.entities.pickup import Pickup
from app.entities.tree import Tree
from app.errors import CommandError, StateError
from app.fsm import IDLE, MOVING, SHOOTING
from app.helpers.geometry import Cell
from app.weapons import WEAPONS
from app.world import World


def make_ready(player, x, y):
    player.cell = Cell(x, y)
    player.machine.state = IDLE
    player.busy_until = 0.0
    player.attack_ready_at = 0.0
    player.immune_until = 0.0
    player.alive = True
    return player


def place_enemy(world, x, y, health=60):
    enemy = make_enemy(id="foe", cell=Cell(x, y), max_health=health)
    world.enemies[enemy.id] = enemy
    return enemy


def test_add_player_spawns_immune_and_spawning(world):
    player = world.add_player("neo", "neo")
    assert player.state == "spawning"
    assert player.is_immune(world.time)
    assert player.health == player.attributes.max_health
    assert player.weapons == ["sword"]


def test_move_advances_one_cell_and_locks(world):
    player = make_ready(world.add_player("neo", "neo"), 5, 5)
    result = world.move(player, "right")
    assert result["moved"] is True
    assert player.cell.as_dict() == {"x": 6, "y": 5}
    assert player.state == MOVING
    assert world.move(player, "right")["reason"] == "busy"


def test_move_blocked_by_solid(world):
    player = make_ready(world.add_player("neo", "neo"), 9, 5)
    result = world.move(player, "right")
    assert result["moved"] is False
    assert result["reason"] == "blocked"
    assert player.cell.as_dict() == {"x": 9, "y": 5}


def test_move_out_of_bounds_is_blocked(world):
    player = make_ready(world.add_player("neo", "neo"), 0, 5)
    assert world.move(player, "left")["reason"] == "blocked"


def test_move_collects_food(world):
    player = make_ready(world.add_player("neo", "neo"), 5, 5)
    player.health = 50
    world.food["f"] = Food("f", Cell(6, 5), 20)
    result = world.move(player, "right")
    assert result["collected"]["kind"] == "food"
    assert player.health == 70
    assert "f" not in world.food


def test_move_collects_coin_and_adds_gold(world):
    player = make_ready(world.add_player("neo", "neo"), 5, 5)
    world.coins["far"] = Coin("far", Cell(1, 1), 9)
    world.coins["c"] = Coin("c", Cell(6, 5), 3)
    result = world.move(player, "right")
    assert result["collected"] == {"kind": "gold", "gold": 3, "total": 3}
    assert player.resources["gold"] == 3
    assert "c" not in world.coins


def test_tick_collects_a_collectible_under_a_standing_player(world):
    player = make_ready(world.add_player("neo", "neo"), 8, 8)
    world.coins["c"] = Coin("c", Cell(8, 8), 5)
    world.tick(1 / 15)
    assert player.resources["gold"] == 5
    assert "c" not in world.coins


def test_tick_collects_a_food_and_coin_stack_on_one_cell(world):
    player = make_ready(world.add_player("neo", "neo"), 8, 8)
    player.health = 50
    world.food["f"] = Food("f", Cell(8, 8), 40)
    world.coins["c"] = Coin("c", Cell(8, 8), 9)
    world.tick(1 / 15)
    assert player.resources["gold"] == 9
    assert player.health == 90
    assert "f" not in world.food and "c" not in world.coins


def test_tick_pickup_skips_a_dead_player(world):
    player = make_ready(world.add_player("neo", "neo"), 8, 8)
    player.alive = False
    world.coins["c"] = Coin("c", Cell(8, 8), 5)
    world.tick(1 / 15)
    assert player.resources["gold"] == 0
    assert "c" in world.coins


def test_move_collects_item_and_changes_attributes(world):
    player = make_ready(world.add_player("neo", "neo"), 5, 5)
    base_vision = player.attributes.vision_range
    world.pickups["p"] = Pickup("p", Cell(6, 5), "spyglass")
    result = world.move(player, "right")
    assert result["collected"]["item"] == "spyglass"
    assert player.attributes.vision_range == base_vision + 2
    assert "spyglass" in player.items


def test_cannot_shoot_while_moving(world):
    player = make_ready(world.add_player("neo", "neo"), 5, 5)
    player.weapons = ["sword", "bow"]
    world.move(player, "right")
    result = world.shoot(player, "right")
    assert result["fired"] is False
    assert result["reason"] == "busy"


def test_attack_hits_and_kills_enemy(world):
    player = make_ready(world.add_player("neo", "neo"), 5, 5)
    enemy = place_enemy(world, 6, 5, health=10)
    result = world.attack(player, "foe")
    assert result["hit"] is True
    assert result["killed"] is True
    assert not enemy.alive
    assert player.kills == 1


def test_attack_out_of_range(world):
    player = make_ready(world.add_player("neo", "neo"), 5, 5)
    place_enemy(world, 8, 5)
    assert world.attack(player, "foe")["reason"] == "out_of_range"


def test_attack_invalid_target(world):
    player = make_ready(world.add_player("neo", "neo"), 5, 5)
    assert world.attack(player, "ghost")["reason"] == "invalid_target"


def test_attack_while_busy_is_blocked(world):
    player = make_ready(world.add_player("neo", "neo"), 5, 5)
    place_enemy(world, 6, 5)
    world.attack(player, "foe")
    assert world.attack(player, "foe")["reason"] == "busy"


def test_attack_cooldown_outlasts_the_swing(world):
    player = make_ready(world.add_player("neo", "neo"), 5, 5)
    place_enemy(world, 6, 5, health=200)
    world.attack(player, "foe")
    weapon = WEAPONS["sword"]

    # the swing animation ends first, then the cooldown keeps the next strike locked out
    world.time += weapon.attack_duration
    world._resolve_busy()
    assert world.attack(player, "foe")["reason"] == "on_cooldown"

    world.time += weapon.cooldown - weapon.attack_duration
    assert world.attack(player, "foe")["hit"] is True


def test_no_melee_weapon(world):
    player = make_ready(world.add_player("neo", "neo"), 5, 5)
    player.weapons = ["bow"]
    assert world.attack(player, "foe")["reason"] == "no_melee_weapon"


def test_shoot_creates_projectile_that_hits(world):
    player = make_ready(world.add_player("neo", "neo"), 3, 5)
    player.weapons = ["sword", "bow"]
    enemy = place_enemy(world, 6, 5, health=100)
    enemy.vision_range = 0
    result = world.shoot(player, "right")
    assert result["fired"] is True
    assert player.state == SHOOTING
    for _ in range(5):
        world.tick(0.1)
    assert enemy.health < 100


def test_no_ranged_weapon(world):
    player = make_ready(world.add_player("neo", "neo"), 5, 5)
    player.weapons = ["sword"]
    assert world.shoot(player, "right")["reason"] == "no_ranged_weapon"


def test_look_around_pulses_vision_and_scans(world):
    player = make_ready(world.add_player("neo", "neo"), 5, 5)
    place_enemy(world, 7, 5)
    before = player.vision_pulse_seq
    result = world.look_around(player)
    assert player.vision_pulse_seq == before + 1
    assert result["visionRange"] == player.attributes.vision_range
    assert any(entry["kind"] == "enemy" for entry in result["visible"])
    assert result["directions"]["right"]["type"] in ("wall", "obstacle", "enemy", "clear", "player")


def test_directional_scan_finds_wall(world):
    player = make_ready(world.add_player("neo", "neo"), 8, 5)
    result = world.look_around(player)
    assert result["directions"]["right"]["type"] == "obstacle"


def test_search_around_filters(world):
    player = make_ready(world.add_player("neo", "neo"), 5, 5)
    place_enemy(world, 6, 5)
    world.coins["c"] = Coin("c", Cell(5, 6), 2)
    result = world.search_around(player, "enemy")
    assert result["count"] == 1
    assert world.search_around(player, "food")["count"] == 0
    assert world.search_around(player, "coin")["matches"][0]["value"] == 2


def test_chop_tree_breaks_and_unblocks(world):
    player = make_ready(world.add_player("neo", "neo"), 5, 5)
    world.trees["t"] = Tree("t", Cell(6, 5))
    assert world._blocked(Cell(6, 5))

    for _ in range(2):
        world.chop(player, "t")
        make_ready(player, 5, 5)

    result = world.chop(player, "t")
    assert result["broken"] is True
    assert result["wood"] == world.settings.wood_per_tree
    assert player.resources["wood"] == world.settings.wood_per_tree
    assert not world._blocked(Cell(6, 5))


def test_chop_is_blocked_while_busy(world):
    player = make_ready(world.add_player("neo", "neo"), 5, 5)
    world.trees["t"] = Tree("t", Cell(6, 5))
    world.chop(player, "t")
    assert world.chop(player, "t")["reason"] == "busy"


def test_chop_out_of_range_and_invalid(world):
    player = make_ready(world.add_player("neo", "neo"), 0, 0)
    world.trees["t"] = Tree("t", Cell(10, 10))
    assert world.chop(player, "t")["reason"] == "out_of_range"
    assert world.chop(player, "missing")["reason"] == "invalid_target"


def test_tree_holds_regrow_while_a_pickup_sits_on_the_stump(world):
    tree = Tree("t", Cell(6, 5), broken=True, hits=0, regrow_at=world.time)
    world.trees["t"] = tree
    world.pickups["p"] = Pickup("p", Cell(6, 5), "spyglass")

    world._regrow_trees()
    assert tree.broken is True

    del world.pickups["p"]
    world._regrow_trees()
    assert tree.broken is False
    assert tree.hits == tree.max_hits


def test_speak_sets_bubble(world):
    player = make_ready(world.add_player("neo", "neo"), 5, 5)
    world.speak(player, "hello")
    assert player.speech_text == "hello"
    assert player.to_view(world.time)["speech"] == "hello"


def test_immunity_blocks_damage(world):
    player = make_ready(world.add_player("neo", "neo"), 5, 5)
    player.immune_until = world.time + 5
    assert world._damage(player, 50, attacker=None) is False
    assert player.health == player.attributes.max_health


def test_death_and_respawn(settings, bare_map):
    fast = AppSettings(respawn_delay_seconds=0.1, spawn_immunity_seconds=5)
    world = World(fast, bare_map, rng=random.Random(1))
    player = make_ready(world.add_player("neo", "neo"), 5, 5)
    world._damage(player, 999, attacker=None)
    assert not player.alive
    assert player.deaths == 1
    for _ in range(3):
        world.tick(0.1)
    assert player.alive
    assert player.is_immune(world.time)


def test_remove_player_drops_projectiles(world):
    player = make_ready(world.add_player("neo", "neo"), 3, 5)
    player.weapons = ["sword", "bow"]
    world.shoot(player, "right")
    world.remove_player("neo")
    assert "neo" not in world.players
    assert all(shot.owner_id != "neo" for shot in world.projectiles.values())


def test_require_player_missing(world):
    with pytest.raises(CommandError):
        world.require_player("nobody")


class _StuckRng:
    def randrange(self, n):
        return 0

    def randint(self, a, b):
        return a


def test_spawn_scans_for_a_free_cell_when_sampling_misses():
    world = World(AppSettings(), make_map(cols=3, rows=1, blocked=[(0, 0)]), rng=_StuckRng())
    assert world._emptiest_spawn().as_dict() == {"x": 1, "y": 0}
    assert world._spawn_within(0, 0, 0).as_dict() == {"x": 1, "y": 0}


def test_spawn_within_avoids_a_collectible_cell():
    world = World(AppSettings(), make_map(cols=3, rows=1), rng=_StuckRng())
    world.coins["c"] = Coin("c", Cell(0, 0), 1)
    assert world._spawn_within(0, 0, 0).as_dict() == {"x": 1, "y": 0}


def test_spawn_raises_when_no_cell_is_free():
    full = make_map(cols=2, rows=1, blocked=[(0, 0), (1, 0)])
    world = World(AppSettings(), full, rng=random.Random(1))
    with pytest.raises(StateError):
        world._emptiest_spawn()


def test_enemy_chases_and_strikes(settings, spawn_map):
    world = World(settings, spawn_map, rng=random.Random(3))
    player = make_ready(world.add_player("neo", "neo"), 10, 10)
    player.immune_until = 0.0
    start = player.health
    for _ in range(80):
        world.tick(0.1)
        if player.health < start:
            break
    assert player.health < start
