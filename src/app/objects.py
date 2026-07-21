from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.errors import MapError


@dataclass(frozen=True, slots=True)
class ObjectKind:
    """A map object's shared properties: how it behaves and whether it blocks movement."""

    name: str
    solid: bool = False
    choppable: bool = False
    collectible: bool = False

    def to_public(self) -> dict[str, Any]:
        return {"solid": self.solid, "choppable": self.choppable, "collectible": self.collectible}


OBJECT_KINDS: dict[str, ObjectKind] = {
    "building": ObjectKind("building", solid=True),
    "rock": ObjectKind("rock", solid=True),
    "bush": ObjectKind("bush"),
    "tree": ObjectKind("tree", choppable=True),
    "item": ObjectKind("item", collectible=True),
}


def get_object_kind(name: str) -> ObjectKind:
    kind = OBJECT_KINDS.get(name)

    if kind is None:
        raise MapError(f"Unknown map object: {name}")

    return kind
