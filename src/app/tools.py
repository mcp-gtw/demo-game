from __future__ import annotations

from typing import Any

from app.classes import CLASSES, DEFAULT_CLASS
from app.colors import DEFAULT_COLOR, PLAYER_COLORS
from app.errors import UnknownCommandError
from app.game import SEARCH_TYPES, GameService
from app.helpers.geometry import DIRECTIONS

_DIRECTIONS = list(DIRECTIONS)
_CLASSES = list(CLASSES)
_COLORS = list(PLAYER_COLORS)


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


# each tool carries its rules in its description, and identity is the session, so none takes a token
TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "login",
        "description": (
            "Join the game with a display name and a class, spawning your character. Call this "
            "first, once per connection: it binds the character to your session so every other "
            "tool acts as you. The name is your unique identity (no two live players share one) "
            "and may only contain letters, numbers, underscores and dashes, up to 32 characters. "
            "Pick a class: warrior (sword, hits hardest), archer (bow, ranged), monk (staff, "
            f"balanced melee) or lancer (spear, reaches two cells). Defaults to {DEFAULT_CLASS} "
            "if omitted. Pick a color for your skin: blue, yellow, purple or black (enemies are "
            f"always red). Defaults to {DEFAULT_COLOR}. On success the browser page drops into the "
            "game following your character."
        ),
        "inputSchema": _schema(
            {
                "name": {"type": "string", "minLength": 1, "maxLength": 32},
                "class": {"type": "string", "enum": _CLASSES},
                "color": {"type": "string", "enum": _COLORS},
            },
            ["name"],
        ),
    },
    {
        "name": "get_player",
        "description": (
            "Return the full state of your character as JSON: position, facing, live state "
            "(idle, moving, attacking, shooting, spawning, dead), health, kills, deaths, carried "
            "items, collected resources (wood, gold), weapons and derived attributes (max health, "
            "move duration, vision range, attack speed)."
        ),
        "inputSchema": _schema({}, []),
    },
    {
        "name": "look_around",
        "description": (
            "Sense your surroundings up to your vision range and emit a vision wave under your "
            "character. Returns yourself and every visible object (players, enemies, food, coins, "
            "items, trees), each with its name, kind, grid position, straight-line distance, step "
            "distance, the cell offset {dx, dy} from you and the direction to walk to reach it, "
            "plus a scan of the four cardinal directions reporting the first wall, obstacle, enemy "
            "or player. Positions are grid cells, never pixels. You cannot see other players' "
            "private items or vision range."
        ),
        "inputSchema": _schema({}, []),
    },
    {
        "name": "search_around",
        "description": (
            "Search your vision range for a single kind of object and return the matches sorted by "
            f"distance. Valid types: {', '.join(SEARCH_TYPES)}."
        ),
        "inputSchema": _schema({"type": {"type": "string", "enum": list(SEARCH_TYPES)}}, ["type"]),
    },
    {
        "name": "move",
        "description": (
            "Step one grid cell in a direction. The server owns movement: it advances your "
            "position by one cell and puts you in the moving state for your move duration. You "
            "cannot move, attack or shoot again until that finishes, and you cannot shoot while "
            "moving. Stepping onto meat heals you, onto a coin adds its gold, and onto an item "
            "collects it. Blocked cells (walls, water, trees, reserved areas) are refused."
        ),
        "inputSchema": _schema(
            {"direction": {"type": "string", "enum": _DIRECTIONS}}, ["direction"]
        ),
    },
    {
        "name": "attack",
        "description": (
            "Melee a target by id with your melee weapon. It must be within the weapon range. "
            "Attacking puts you in the attacking state for the weapon's attack duration and cannot "
            "be repeated until the weapon's cooldown elapses. Immune targets take no damage. "
            "Defeating an enemy rewards you with gold."
        ),
        "inputSchema": _schema({"targetId": {"type": "string"}}, ["targetId"]),
    },
    {
        "name": "shoot",
        "description": (
            "Fire your ranged weapon in a direction (defaults to the way you are facing). The "
            "projectile travels in a straight line until it hits or leaves range. You cannot shoot "
            "while moving or busy, and not again until the weapon's cooldown elapses."
        ),
        "inputSchema": _schema({"direction": {"type": "string", "enum": _DIRECTIONS}}, []),
    },
    {
        "name": "chop",
        "description": (
            "Chop a tree by id when you stand next to it. Each chop swings your melee weapon and "
            "briefly locks you in the attacking state. Trees take several hits to fall and regrow "
            "later. A fallen tree stops blocking movement and rewards you with wood."
        ),
        "inputSchema": _schema({"targetId": {"type": "string"}}, ["targetId"]),
    },
    {
        "name": "speak",
        "description": (
            "Say a short line that appears as a speech bubble above your character for a few "
            "seconds. Up to 50 characters. Any characters are allowed — letters (including accents "
            "and other scripts), numbers, punctuation, symbols and emoji — the only thing rejected "
            "is tabs and line breaks, since it must be a single line."
        ),
        "inputSchema": _schema(
            {"text": {"type": "string", "minLength": 1, "maxLength": 50}}, ["text"]
        ),
    },
    {
        "name": "weapons",
        "description": (
            "List the weapons you carry with their stats: kind (melee or ranged), damage, range, "
            "attack duration and cooldown."
        ),
        "inputSchema": _schema({}, []),
    },
]


def dispatch(
    game: GameService, player_id: str | None, name: str, arguments: dict[str, Any]
) -> dict[str, Any]:
    if name == "get_player":
        return game.get_player(player_id)

    if name == "look_around":
        return game.look_around(player_id)

    if name == "search_around":
        return game.search_around(player_id, arguments["type"])

    if name == "move":
        return game.move(player_id, arguments["direction"])

    if name == "attack":
        return game.attack(player_id, arguments["targetId"])

    if name == "shoot":
        return game.shoot(player_id, arguments.get("direction"))

    if name == "chop":
        return game.chop(player_id, arguments["targetId"])

    if name == "speak":
        return game.speak(player_id, arguments["text"])

    if name == "weapons":
        return game.weapons(player_id)

    raise UnknownCommandError(f"Unknown tool: {name}")
