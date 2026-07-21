import random

import pytest

from app.errors import CommandError
from app.fsm import IDLE
from app.game import GameService
from app.world import World


def make_game(settings, bare_map):
    world = World(settings, bare_map, rng=random.Random(5))
    return GameService(world, settings), world


def ready(world, player):
    player.machine.state = IDLE
    player.busy_until = 0.0
    player.immune_until = 0.0


def test_login_returns_the_player(settings, bare_map):
    game, _ = make_game(settings, bare_map)
    result = game.login("Neo_1")
    assert "token" not in result
    assert result["player"]["name"] == "Neo_1"
    assert result["player"]["class"] == "warrior"


def test_login_picks_the_chosen_class(settings, bare_map):
    game, world = make_game(settings, bare_map)
    player = game.login("Robin", "archer")["player"]
    assert player["class"] == "archer"
    assert world.players["Robin"].sprite == "archer"
    assert [weapon["id"] for weapon in player["weapons"]] == ["bow"]


def test_login_rejects_unknown_class(settings, bare_map):
    game, _ = make_game(settings, bare_map)
    with pytest.raises(CommandError):
        game.login("Rogue", "ninja")


def test_login_picks_the_chosen_color(settings, bare_map):
    game, world = make_game(settings, bare_map)
    player = game.login("Ivy", "warrior", "purple")["player"]
    assert player["color"] == "purple"
    assert world.players["Ivy"].color == "purple"


def test_login_defaults_to_blue(settings, bare_map):
    game, _ = make_game(settings, bare_map)
    assert game.login("Ash")["player"]["color"] == "blue"


def test_login_rejects_unknown_color(settings, bare_map):
    game, _ = make_game(settings, bare_map)
    with pytest.raises(CommandError):
        game.login("Rogue", "warrior", "turquoise")


def test_login_rejects_bad_name(settings, bare_map):
    game, _ = make_game(settings, bare_map)
    with pytest.raises(CommandError):
        game.login("bad name!")


def test_login_rejects_too_long(settings, bare_map):
    game, _ = make_game(settings, bare_map)
    with pytest.raises(CommandError):
        game.login("x" * 33)


def test_login_rejects_duplicate(settings, bare_map):
    game, _ = make_game(settings, bare_map)
    game.login("neo")
    with pytest.raises(CommandError):
        game.login("neo")


def test_player_state_by_id(settings, bare_map):
    game, world = make_game(settings, bare_map)
    player_id = game.login("neo")["player"]["id"]
    assert game.player_state(player_id)["name"] == "neo"
    world.remove_player(player_id)
    assert game.player_state(player_id) is None


def test_tools_require_login_first(settings, bare_map):
    game, _ = make_game(settings, bare_map)
    with pytest.raises(CommandError):
        game.get_player(None)
    with pytest.raises(CommandError):
        game.look_around("")


def test_absent_player_is_rejected(settings, bare_map):
    game, world = make_game(settings, bare_map)
    player_id = game.login("neo")["player"]["id"]
    world.remove_player(player_id)
    with pytest.raises(CommandError):
        game.get_player(player_id)


def test_full_action_flow(settings, bare_map):
    game, world = make_game(settings, bare_map)
    player_id = game.login("neo")["player"]["id"]
    player = world.players[player_id]
    ready(world, player)
    player.cell.x = 5
    player.cell.y = 5
    assert game.move(player_id, "right")["moved"] is True
    assert "weapons" in game.weapons(player_id)
    assert game.get_player(player_id)["name"] == "neo"


def test_search_around_validates_type(settings, bare_map):
    game, _ = make_game(settings, bare_map)
    player_id = game.login("neo")["player"]["id"]
    with pytest.raises(CommandError):
        game.search_around(player_id, "banana")
    assert game.search_around(player_id, "enemy")["type"] == "enemy"


def test_speak_validation(settings, bare_map):
    game, _ = make_game(settings, bare_map)
    player_id = game.login("neo")["player"]["id"]
    assert game.speak(player_id, "hi there")["said"] == "hi there"
    with pytest.raises(CommandError):
        game.speak(player_id, "line\nbreak")
    with pytest.raises(CommandError):
        game.speak(player_id, "x" * 51)
