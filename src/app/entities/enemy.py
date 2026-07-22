from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.fsm import StateMachine
from app.helpers.geometry import Cell
from app.npcs.behavior import Behavior


@dataclass(slots=True)
class Enemy:
    """A server-driven NPC bound to the spawn point it was born from."""

    id: str
    entity: str
    cell: Cell
    max_health: int
    spawn_index: int
    damage: int
    vision_range: int
    attack_range: int
    speed_duration: float
    attack_cooldown: float
    attack_duration: float
    respawn_seconds: float
    behavior: Behavior
    ranged: bool
    projectile_speed: int
    flee_range: int
    flee_when_attacked: bool
    spook_seconds: float
    wander_pause: tuple[float, float]
    facing: str = "down"
    health: int = 0
    alive: bool = True
    machine: StateMachine = field(default_factory=StateMachine)
    busy_until: float = 0.0
    attack_ready_at: float = 0.0
    spooked_until: float = 0.0
    wander_ready_at: float = 0.0
    respawn_at: float | None = None

    def __post_init__(self) -> None:
        if self.health == 0:
            self.health = self.max_health

    @property
    def state(self) -> str:
        return self.machine.state

    def to_public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": "enemy",
            "name": self.entity,
            "position": self.cell.as_dict(),
            "facing": self.facing,
            "state": self.state,
            "health": self.health,
            "maxHealth": self.max_health,
            "alive": self.alive,
            "moveMs": round(self.speed_duration * 1000),
        }
