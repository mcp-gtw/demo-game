from __future__ import annotations

from app.errors import MapError
from app.items import ITEMS
from app.npcs.behavior import Behavior
from app.npcs.enemy_spec import EnemySpec
from app.npcs.loot_drop import LootDrop

ENEMIES: dict[str, EnemySpec] = {
    "enemy_warrior": EnemySpec(
        entity="enemy_warrior",
        sprite="warrior",
        max_health=45,
        damage=5,
        vision_range=5,
        attack_range=1,
        speed_duration=1.5,
        attack_cooldown=2.5,
        respawn_seconds=120.0,
        behavior=Behavior.AGGRESSIVE,
        loot=(LootDrop("gold", 5, 1.0), LootDrop("food", 20, 0.35)),
    ),
    "enemy_archer": EnemySpec(
        entity="enemy_archer",
        sprite="archer",
        max_health=30,
        damage=3,
        vision_range=6,
        attack_range=4,
        speed_duration=1.4,
        attack_cooldown=2.5,
        respawn_seconds=120.0,
        behavior=Behavior.AGGRESSIVE,
        ranged=True,
        projectile_speed=2,
        loot=(LootDrop("gold", 4, 1.0),),
    ),
    "enemy_lancer": EnemySpec(
        entity="enemy_lancer",
        sprite="lancer",
        max_health=55,
        damage=6,
        vision_range=5,
        attack_range=2,
        speed_duration=1.7,
        attack_cooldown=2.6,
        respawn_seconds=120.0,
        behavior=Behavior.AGGRESSIVE,
        loot=(LootDrop("gold", 6, 1.0), LootDrop("food", 20, 0.3)),
    ),
    "enemy_monk": EnemySpec(
        entity="enemy_monk",
        sprite="monk",
        max_health=40,
        damage=4,
        vision_range=6,
        attack_range=1,
        speed_duration=1.5,
        attack_cooldown=2.2,
        respawn_seconds=120.0,
        behavior=Behavior.AGGRESSIVE,
        loot=(LootDrop("gold", 5, 1.0), LootDrop("heart", 1, 0.12)),
    ),
    "sheep_shy": EnemySpec(
        entity="sheep_shy",
        sprite="sheep",
        max_health=18,
        damage=0,
        vision_range=5,
        attack_range=0,
        speed_duration=2.1,
        attack_cooldown=1.0,
        respawn_seconds=120.0,
        behavior=Behavior.SKITTISH,
        flee_range=4,
        loot=(LootDrop("food", 25, 0.8), LootDrop("gold", 3, 0.5)),
    ),
    "sheep_flighty": EnemySpec(
        entity="sheep_flighty",
        sprite="sheep",
        max_health=18,
        damage=0,
        vision_range=5,
        attack_range=0,
        speed_duration=1.9,
        attack_cooldown=1.0,
        respawn_seconds=120.0,
        behavior=Behavior.WANDER,
        flee_when_attacked=True,
        spook_seconds=4.0,
        loot=(LootDrop("food", 25, 0.7), LootDrop("boots", 1, 0.15)),
    ),
    "sheep_calm": EnemySpec(
        entity="sheep_calm",
        sprite="sheep",
        max_health=22,
        damage=0,
        vision_range=4,
        attack_range=0,
        speed_duration=2.3,
        attack_cooldown=1.0,
        respawn_seconds=120.0,
        behavior=Behavior.WANDER,
        loot=(LootDrop("food", 25, 1.0), LootDrop("heart", 1, 0.2)),
    ),
}


def _validate_loot(enemies: dict[str, EnemySpec]) -> None:
    # food drops meat, an item id drops that pickup, and everything else becomes a gold coin, so
    # gold is the only resource that maps to a coin
    valid = {"food", "gold", *ITEMS}

    for spec in enemies.values():
        for drop in spec.loot:
            if drop.resource not in valid:
                raise MapError(f"Enemy '{spec.entity}' drops an unknown resource '{drop.resource}'")


_validate_loot(ENEMIES)


def get_enemy_spec(entity: str) -> EnemySpec:
    spec = ENEMIES.get(entity)

    if spec is None:
        raise MapError(f"Unknown enemy entity: {entity}")

    return spec
