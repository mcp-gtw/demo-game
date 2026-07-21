from __future__ import annotations

from dataclasses import dataclass

from app.errors import CommandError


@dataclass(frozen=True, slots=True)
class ClassSpec:
    """A playable class: the sprite it renders as and the weapons it starts with."""

    id: str
    sprite: str
    weapons: tuple[str, ...]


CLASSES: dict[str, ClassSpec] = {
    "warrior": ClassSpec("warrior", "warrior", ("sword",)),
    "archer": ClassSpec("archer", "archer", ("bow",)),
    "monk": ClassSpec("monk", "monk", ("staff",)),
    "lancer": ClassSpec("lancer", "lancer", ("spear",)),
}

DEFAULT_CLASS = "warrior"


def get_class(class_id: str | None) -> ClassSpec:
    spec = CLASSES.get(class_id or DEFAULT_CLASS)

    if spec is None:
        raise CommandError(f"Unknown class, choose one of: {', '.join(CLASSES)}")

    return spec
