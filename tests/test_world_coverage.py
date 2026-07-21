import random

from conftest import make_map
from test_world import make_ready, place_enemy

from app.entities.food import Food
from app.entities.pickup import Pickup
from app.entities.tree import Tree
from app.helpers.geometry import Cell
from app.world import World


def test_projectile_expires_at_range_limit(world):
    player = make_ready(world.add_player("neo", "neo"), 5, 5)
    player.weapons = ["sword", "bow"]
    world.shoot(player, "down")
    for _ in range(8):
        world.tick(0.1)
    assert not world.projectiles


def test_projectile_passes_through_immune_player(world):
    shooter = make_ready(world.add_player("a", "a"), 3, 5)
    shooter.weapons = ["sword", "bow"]
    bystander = make_ready(world.add_player("b", "b"), 6, 5)
    bystander.immune_until = world.time + 5
    world.shoot(shooter, "right")
    for _ in range(4):
        world.tick(0.1)
    assert bystander.health == bystander.attributes.max_health


def test_attack_self_is_invalid(world):
    player = make_ready(world.add_player("neo", "neo"), 5, 5)
    assert world.attack(player, "neo")["reason"] == "invalid_target"


def test_move_over_empty_cell_with_collectibles_elsewhere(world):
    player = make_ready(world.add_player("neo", "neo"), 5, 5)
    world.food["f"] = Food("f", Cell(0, 0), 10)
    world.pickups["pk"] = Pickup("pk", Cell(1, 1), "boots")
    result = world.move(player, "right")
    assert result["collected"] is None


def test_visible_skips_dead_enemy_and_lists_tree(world):
    player = make_ready(world.add_player("neo", "neo"), 5, 5)
    dead = place_enemy(world, 6, 5)
    dead.alive = False
    world.trees["t"] = Tree("t", Cell(5, 6))
    world.trees["broken"] = Tree("broken", Cell(5, 7), broken=True)
    kinds = [entry["kind"] for entry in world.look_around(player)["visible"]]
    assert "tree" in kinds
    assert "enemy" not in kinds


def test_replenish_skips_when_no_free_cell(settings):
    blocked = [(x, y) for x in range(2) for y in range(2)]
    game_map = make_map(cols=2, rows=2, blocked=blocked, food_cap=5)
    world = World(settings, game_map, rng=random.Random(1))
    world._next_food_at = 0.0
    world._replenish_food()
    assert len(world.food) == 0
    assert world._next_food_at > 0.0


def test_map_objects_load_items_and_trees(settings):
    game_map = make_map(cols=10, rows=10, trees=[(2, 2)], pickups=[(3, 3, "boots")])
    world = World(settings, game_map, rng=random.Random(1))
    assert any(tree.cell.equals(Cell(2, 2)) for tree in world.trees.values())
    assert any(pickup.item == "boots" for pickup in world.pickups.values())
    assert len(world.trees) == 1
