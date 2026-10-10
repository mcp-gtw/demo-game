import asyncio

from mcp import ClientSession


async def move_player(session: ClientSession) -> bool:
    for _ in range(50):
        player = await session.call_tool("get_player", {})
        assert not player.is_error

        if player.structured_content["state"] == "idle":
            break

        await asyncio.sleep(0.1)
    else:
        raise AssertionError("Player did not finish the entry animation")

    before = player.structured_content

    for direction in [
        "down",
        "right",
        "up",
        "left",
        "down_right",
        "down_left",
        "up_right",
        "up_left",
    ]:
        movement = await session.call_tool("move", {"direction": direction})
        assert not movement.is_error

        if movement.structured_content["moved"]:
            after = await session.call_tool("get_player", {})
            assert not after.is_error
            assert after.structured_content["id"] == before["id"]
            assert after.structured_content["position"] != before["position"]
            return True

        assert movement.structured_content["reason"] == "blocked"

    raise AssertionError("The player has no reachable adjacent cell")
