import random

import pytest

from app.errors import UnknownCommandError
from app.game import GameService
from app.tools import TOOL_DEFINITIONS, dispatch
from app.world import World


def make_game(settings, bare_map):
    return GameService(World(settings, bare_map, rng=random.Random(2)), settings)


def test_definitions_are_well_formed():
    names = {tool["name"] for tool in TOOL_DEFINITIONS}
    assert {"login", "move", "attack", "shoot", "look_around", "search_around", "speak"} <= names
    for tool in TOOL_DEFINITIONS:
        assert tool["description"]
        assert tool["inputSchema"]["type"] == "object"


def test_no_tool_takes_a_token():
    for tool in TOOL_DEFINITIONS:
        assert "token" not in tool["inputSchema"]["properties"]

    login = next(tool for tool in TOOL_DEFINITIONS if tool["name"] == "login")
    assert login["inputSchema"]["required"] == ["name"]


def test_dispatch_routes_every_gameplay_tool(settings, bare_map):
    game = make_game(settings, bare_map)
    player_id = game.login("neo")["player"]["id"]
    player = game.world.players[player_id]
    player.machine.state = "idle"
    player.busy_until = 0.0

    assert dispatch(game, player_id, "get_player", {})["name"] == "neo"
    assert "visible" in dispatch(game, player_id, "look_around", {})
    assert dispatch(game, player_id, "search_around", {"type": "food"})["type"] == "food"
    assert "moved" in dispatch(game, player_id, "move", {"direction": "right"})
    assert "hit" in dispatch(game, player_id, "attack", {"targetId": "ghost"})
    assert "fired" in dispatch(game, player_id, "shoot", {})
    assert "chopped" in dispatch(game, player_id, "chop", {"targetId": "none"})
    assert dispatch(game, player_id, "speak", {"text": "olá!"})["said"] == "olá!"
    assert "weapons" in dispatch(game, player_id, "weapons", {})


def test_login_and_unknown_tools_are_not_dispatched(settings, bare_map):
    game = make_game(settings, bare_map)
    with pytest.raises(UnknownCommandError):
        dispatch(game, "neo", "login", {"name": "neo"})
    with pytest.raises(UnknownCommandError):
        dispatch(game, "neo", "teleport", {})
