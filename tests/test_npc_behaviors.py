from conftest import make_enemy
from test_world import make_ready, place_enemy

from app.helpers.geometry import Cell
from app.npcs.behavior import Behavior


class SeqRandom:
    def __init__(self, values):
        self.values = list(values)
        self.index = 0

    def random(self):
        value = self.values[self.index % len(self.values)]
        self.index += 1
        return value

    def choice(self, sequence):
        return sequence[0]


def _enemy(world, x, y, **kwargs):
    enemy = make_enemy(cell=Cell(x, y), max_health=50, damage=5, **kwargs)
    world.enemies["foe"] = enemy
    return enemy


def test_skittish_enemy_flees_from_a_nearby_player(world):
    player = make_ready(world.add_player("neo", "neo"), 5, 7)
    player.immune_until = 0.0
    enemy = _enemy(world, 5, 5, behavior=Behavior.SKITTISH, flee_range=4)
    world._advance_enemies()
    assert enemy.cell.equals(Cell(5, 4))


def test_skittish_enemy_wanders_when_no_player_is_near(world):
    enemy = _enemy(world, 5, 5, behavior=Behavior.SKITTISH, flee_range=4, wander_chance=1.0)
    world.rng = SeqRandom([0.0])
    world._advance_enemies()
    assert enemy.state == "moving"


def test_wander_enemy_roams_or_rests_on_its_chance(world):
    roamer = _enemy(world, 5, 5, behavior=Behavior.WANDER, wander_chance=1.0)
    world.rng = SeqRandom([0.0])
    world._advance_enemies()
    assert roamer.state == "moving"

    rester = _enemy(world, 8, 8, behavior=Behavior.WANDER, wander_chance=0.0)
    world.rng = SeqRandom([0.5])
    world._advance_enemies()
    assert rester.state == "idle"


def test_flee_when_attacked_spooks_then_flees(world):
    player = make_ready(world.add_player("neo", "neo"), 5, 7)
    player.immune_until = 0.0
    enemy = _enemy(
        world, 5, 5, behavior=Behavior.WANDER, flee_when_attacked=True, spook_seconds=5.0
    )

    world._damage(enemy, 10, attacker=player)
    assert enemy.spooked_until == world.time + 5.0

    world._advance_enemies()
    assert enemy.cell.equals(Cell(5, 4))


def test_loot_drops_a_gold_coin_and_food_when_the_rolls_succeed(world):
    make_ready(world.add_player("neo", "neo"), 5, 5)
    enemy = place_enemy(world, 6, 5)
    world.rng = SeqRandom([0.0, 0.0])
    world._drop_loot(enemy)
    assert any(c.value == 5 and c.cell.equals(enemy.cell) for c in world.coins.values())
    assert any(food.cell.equals(enemy.cell) for food in world.food.values())


def test_loot_drops_an_item_pickup(world):
    make_ready(world.add_player("neo", "neo"), 5, 5)
    sheep = make_enemy(
        id="s",
        entity="sheep_flighty",
        cell=Cell(6, 5),
        max_health=18,
        damage=0,
        vision_range=5,
        attack_range=0,
        speed_duration=0.8,
        respawn_seconds=10.0,
    )
    world.enemies["s"] = sheep
    world.rng = SeqRandom([0.0, 0.0])
    world._drop_loot(sheep)
    assert any(pickup.item == "boots" for pickup in world.pickups.values())


def test_loot_skips_a_drop_when_its_roll_fails(world):
    make_ready(world.add_player("neo", "neo"), 5, 5)
    enemy = place_enemy(world, 6, 5)
    world.rng = SeqRandom([0.0, 0.9])
    before = len(world.food)
    world._drop_loot(enemy)
    assert any(c.value == 5 for c in world.coins.values())
    assert len(world.food) == before
