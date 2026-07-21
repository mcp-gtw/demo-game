from __future__ import annotations

from dataclasses import dataclass

from app.errors import StateError

# every actor state used across the game
IDLE = "idle"
MOVING = "moving"
ATTACKING = "attacking"
SHOOTING = "shooting"
SPAWNING = "spawning"
DEAD = "dead"

# the transitions any actor is allowed to make between states
ACTOR_TRANSITIONS: dict[str, set[str]] = {
    IDLE: {MOVING, ATTACKING, SHOOTING, DEAD, SPAWNING},
    MOVING: {IDLE, DEAD},
    ATTACKING: {IDLE, DEAD},
    SHOOTING: {IDLE, DEAD},
    SPAWNING: {IDLE, DEAD},
    DEAD: {SPAWNING},
}


@dataclass(slots=True)
class StateMachine:
    """A tiny transition-validating state machine shared by every actor in the world."""

    state: str = IDLE

    def can(self, target: str) -> bool:
        return target in ACTOR_TRANSITIONS[self.state]

    def to(self, target: str) -> None:
        if not self.can(target):
            raise StateError(f"Cannot move from {self.state!r} to {target!r}")

        self.state = target

    def is_busy(self) -> bool:
        return self.state in (MOVING, ATTACKING, SHOOTING, SPAWNING)
