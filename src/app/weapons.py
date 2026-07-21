from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MELEE = "melee"
RANGED = "ranged"


@dataclass(frozen=True, slots=True)
class WeaponSpec:
    """The immutable stats of a weapon. Players may carry more than one."""

    id: str
    name: str
    kind: str
    damage: int
    range: int
    attack_duration: float
    cooldown: float
    projectile: str | None = None
    projectile_speed: int = 0

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "damage": self.damage,
            "range": self.range,
            "attackDuration": round(self.attack_duration, 3),
            "cooldown": round(self.cooldown, 3),
            "projectile": self.projectile,
        }


# the melee sword out-damages the ranged bow, so trading reach costs damage
WEAPONS: dict[str, WeaponSpec] = {
    "sword": WeaponSpec(
        id="sword",
        name="Sword",
        kind=MELEE,
        damage=40,
        range=1,
        attack_duration=0.45,
        cooldown=0.6,
    ),
    "bow": WeaponSpec(
        id="bow",
        name="Bow",
        kind=RANGED,
        damage=20,
        range=7,
        attack_duration=0.4,
        cooldown=0.5,
        projectile="arrow",
        projectile_speed=2,
    ),
    "staff": WeaponSpec(
        id="staff",
        name="Staff",
        kind=MELEE,
        damage=28,
        range=1,
        attack_duration=0.5,
        cooldown=0.65,
    ),
    "spear": WeaponSpec(
        id="spear",
        name="Spear",
        kind=MELEE,
        damage=34,
        range=2,
        attack_duration=0.5,
        cooldown=0.8,
    ),
}
