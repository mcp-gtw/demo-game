from __future__ import annotations

from app.errors import CommandError

# the skins a player may pick at login. Enemies always render red, so red is not offered to players.
PLAYER_COLORS: tuple[str, ...] = ("blue", "yellow", "purple", "black")

DEFAULT_COLOR = "blue"


def get_color(color: str | None) -> str:
    chosen = color or DEFAULT_COLOR

    if chosen not in PLAYER_COLORS:
        raise CommandError(f"Unknown color, choose one of: {', '.join(PLAYER_COLORS)}")

    return chosen
