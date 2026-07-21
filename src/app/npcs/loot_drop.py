from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LootDrop:
    """A chance to grant a resource to the killer, or to drop food where the NPC fell."""

    resource: str
    amount: int
    chance: float
