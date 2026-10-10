import asyncio
import json
import sys

import httpx2
from gameplay import move_player
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


async def main():
    config = json.loads(sys.stdin.read())
    async with (
        httpx2.AsyncClient(
            verify=False, headers={"Authorization": "Bearer " + config["token"]}
        ) as http,
        streamable_http_client(config["url"], http_client=http) as (read, write),
        ClientSession(read, write) as session,
    ):
        await session.discover()
        listed = await session.list_tools()
        assert len(listed.tools) == 10
        assert {"login", "move", "get_player"} <= {tool.name for tool in listed.tools}
        if config.get("name") is None:
            player = await session.call_tool("get_player", {})
            assert not player.is_error
            moved = await move_player(session) if config.get("move") else None
            print(json.dumps({"player": player.structured_content, "move": moved}))
            return

        login = await session.call_tool(
            "login",
            {"name": config["name"], "class": "warrior"},
            meta={"openai/locale": "en-US", "openai/userAgent": "ChatGPT"},
        )
        assert not login.is_error, login
        player = await session.call_tool("get_player", {})
        assert not player.is_error, player
        moved = await move_player(session)
        print(
            json.dumps(
                {
                    "tools": len(listed.tools),
                    "login": not login.is_error,
                    "player": player.structured_content,
                    "move": moved,
                }
            )
        )


asyncio.run(main())
