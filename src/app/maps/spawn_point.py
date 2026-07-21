from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class SpawnPoint:
    """An NPC origin the server respawns from, inside a radius, up to a maximum."""

    entity: str
    x: int
    y: int
    range: int
    max: int
