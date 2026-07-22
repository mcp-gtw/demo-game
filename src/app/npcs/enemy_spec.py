from __future__ import annotations

from dataclasses import dataclass, field

from app.npcs.behavior import Behavior
from app.npcs.loot_drop import LootDrop


@dataclass(frozen=True, slots=True)
class EnemySpec:
    """Everything an NPC is born with, so a new profile is one entry with no engine changes."""

    entity: str
    sprite: str
    max_health: int
    damage: int
    vision_range: int
    attack_range: int
    speed_duration: float
    attack_cooldown: float
    respawn_seconds: float
    attack_duration: float = 0.4
    behavior: Behavior = Behavior.AGGRESSIVE
    ranged: bool = False
    projectile_speed: int = 0
    flee_range: int = 0
    flee_when_attacked: bool = False
    spook_seconds: float = 0.0
    wander_pause: tuple[float, float] = (3.0, 10.0)
    loot: tuple[LootDrop, ...] = field(default_factory=tuple)
