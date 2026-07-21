from app.config import AppSettings
from app.room_manager import DEFAULT_ROOM_ID, RoomManager


def test_default_room_exists_from_startup():
    manager = RoomManager(AppSettings())
    assert manager.default.id == DEFAULT_ROOM_ID
    assert [room.id for room in manager.all()] == [DEFAULT_ROOM_ID]


def test_rooms_are_isolated():
    manager = RoomManager(AppSettings())
    dungeon = manager.create("dungeon")
    assert {room.id for room in manager.all()} == {DEFAULT_ROOM_ID, "dungeon"}

    manager.default.game.login("hero")
    assert [player.name for player in manager.default.world.players.values()] == ["hero"]
    assert not dungeon.world.players
