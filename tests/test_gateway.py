import asyncio
import contextlib
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.config import AppSettings
from app.gateway import AppGateway, _channel_id_for
from app.provider import LocalProvider
from app.session import Session
from mcp_gtw.errors import ChannelCapacityError

TOKEN = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_DISCONNECT = object()


def build_gateway(grace=0.02):
    return AppGateway(app_settings=AppSettings(session_grace_seconds=grace))


async def drain():
    pending = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]

    for task in pending:
        task.cancel()

    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


class FakeWebSocket:
    def __init__(self, token=None):
        self.query_params = {"token": token} if token else {}
        self.url = SimpleNamespace(scheme="ws", netloc="test")
        self.sent = []
        self.closed = None
        self._queue = asyncio.Queue()

    async def accept(self):
        return None

    async def close(self, code=1000):
        self.closed = code

    async def send_json(self, data):
        self.sent.append(data)

    async def receive_text(self):
        item = await self._queue.get()

        if item is _DISCONNECT:
            raise WebSocketDisconnect(1000)

        return item

    def push(self, text):
        self._queue.put_nowait(text)

    def disconnect(self):
        self._queue.put_nowait(_DISCONNECT)

    def types(self):
        return [message["type"] for message in self.sent]


def test_http_surface():
    with TestClient(build_gateway().create_app()) as client:
        assert client.get("/").status_code == 200
        assert client.get("/health").json()["status"] == "ok"
        assert client.get("/play").status_code == 404

        info = client.get("/app/info").json()
        assert set(info) == {"playersOnline", "tools"}
        assert info["playersOnline"] == 0
        names = {tool["name"] for tool in info["tools"]}
        assert {"login", "move", "speak"} <= names

        static = client.get("/static/assets/terrain/water.png")
        assert static.headers["cache-control"] == "no-cache"


def test_session_handshake_sends_the_stable_connect_info():
    client = TestClient(build_gateway().create_app())
    with client, client.websocket_connect(f"/app/stream?token={TOKEN}") as ws:
        message = ws.receive_json()
        assert message["type"] == "session"
        assert message["mcpToken"] == f"mcp-{TOKEN}"
        assert f"/mcp/{_channel_id_for(TOKEN)}" in message["mcpUrl"]


def test_stream_rejects_a_missing_or_malformed_token():
    with TestClient(build_gateway().create_app()) as client:
        for bad in ("", "?token=not-a-uuid"):
            with (
                contextlib.suppress(WebSocketDisconnect),
                client.websocket_connect(f"/app/stream{bad}") as ws,
            ):
                ws.receive_json()
                raise AssertionError("the connection should have been refused")


async def _run_until_session(gateway, ws):
    task = asyncio.create_task(gateway.stream_endpoint(ws))
    await asyncio.sleep(0.02)
    return task, next(iter(gateway._sessions.values()))


async def test_login_starts_the_game_then_disconnect_removes_the_player():
    gateway = build_gateway()
    ws = FakeWebSocket(token=TOKEN)
    task, session = await _run_until_session(gateway, ws)

    assert ws.sent[0]["type"] == "session"

    session.adopt(session.room.game.login("neo")["player"]["id"])
    await asyncio.sleep(0.02)

    assert {"login", "catalog", "map", "snapshot"} <= set(ws.types())

    ws.disconnect()
    with contextlib.suppress(WebSocketDisconnect):
        await task
    await session.teardown
    assert "neo" not in gateway.rooms.default.world.players
    await drain()


async def test_socket_answers_ping_and_me():
    gateway = build_gateway()
    ws = FakeWebSocket()
    session = Session(channel_id="c", mcp_token="m", room=gateway.rooms.default)

    await gateway._handle_message(ws, session, '{"type":"ping","id":7}')
    assert ws.sent[-1] == {"type": "pong", "id": 7}

    await gateway._handle_message(ws, session, "not json")
    await gateway._handle_message(ws, session, '{"type":"me"}')
    assert ws.sent[-1] == {"type": "pong", "id": 7}

    player_id = session.room.game.login("neo")["player"]["id"]
    session.adopt(player_id)
    await gateway._handle_message(ws, session, '{"type":"me"}')
    assert ws.sent[-1]["type"] == "me"
    assert ws.sent[-1]["player"]["name"] == "neo"

    gateway.rooms.default.world.remove_player(player_id)
    before = len(ws.sent)
    await gateway._handle_message(ws, session, '{"type":"me"}')
    assert len(ws.sent) == before  # absent player sends nothing
    await drain()


async def test_the_same_token_reuses_one_channel_and_session():
    gateway = build_gateway()
    first = await gateway._acquire_session(TOKEN)
    second = await gateway._acquire_session(TOKEN)

    assert first is second
    assert first.mcp_token == f"mcp-{TOKEN}"
    assert first.channel_id == _channel_id_for(TOKEN)
    assert list(gateway._sessions) == [first.channel_id]
    await drain()


async def test_acquire_session_rejects_a_bad_token():
    gateway = build_gateway()
    assert await gateway._acquire_session(None) is None
    assert await gateway._acquire_session("token-paulo") is None
    await drain()


async def test_identity_channel_reuses_an_existing_channel():
    gateway = build_gateway()
    channel_id = _channel_id_for(TOKEN)
    channel = await gateway.create_channel(
        channel_id=channel_id, mcp_token=f"mcp-{TOKEN}", ttl_seconds=float("inf")
    )
    assert await gateway._identity_channel(channel_id, TOKEN) is channel
    await drain()


async def test_identity_channel_converges_when_creation_races():
    gateway = build_gateway()
    channel_id = _channel_id_for(TOKEN)
    channel = await gateway.create_channel(
        channel_id=channel_id, mcp_token=f"mcp-{TOKEN}", ttl_seconds=float("inf")
    )
    gateway.registry.get = Mock(side_effect=[None, channel])
    gateway.create_channel = AsyncMock(side_effect=ChannelCapacityError("race"))
    assert await gateway._identity_channel(channel_id, TOKEN) is channel
    await drain()


async def test_acquire_session_denies_when_at_capacity():
    gateway = build_gateway()
    gateway.registry.get = Mock(return_value=None)
    gateway.create_channel = AsyncMock(side_effect=ChannelCapacityError("full"))
    assert await gateway._acquire_session(TOKEN) is None
    await drain()


async def test_stream_endpoint_closes_on_a_refused_token():
    gateway = build_gateway()
    ws = FakeWebSocket()
    await gateway.stream_endpoint(ws)
    assert ws.closed == 1008
    assert ws.sent == []
    await drain()


async def test_session_resumes_after_a_reconnect():
    gateway = build_gateway(grace=0.5)
    first = FakeWebSocket(token=TOKEN)
    task, session = await _run_until_session(gateway, first)
    session.adopt(session.room.game.login("neo")["player"]["id"])
    await asyncio.sleep(0)

    first.disconnect()
    with contextlib.suppress(WebSocketDisconnect):
        await task
    assert session.teardown is not None

    second = FakeWebSocket(token=TOKEN)
    task2 = asyncio.create_task(gateway.stream_endpoint(second))
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert _channel_id_for(TOKEN) in gateway._sessions
    names = {player.name for player in gateway.rooms.default.world.players.values()}
    assert "neo" in names
    assert "login" in second.types()

    second.disconnect()
    with contextlib.suppress(WebSocketDisconnect):
        await task2
    await session.teardown
    await drain()


async def test_second_login_on_a_session_is_rejected():
    gateway = build_gateway()
    channel = await gateway.create_channel(ttl_seconds=float("inf"))
    session = Session(channel_id=channel.channel_id, mcp_token="m", room=gateway.rooms.default)
    provider = LocalProvider(channel, session)
    await provider.start()

    first = await channel.execute_tool(name="login", arguments={"name": "neo"})
    assert not first.isError
    assert gateway.rooms.default.world.players[session.player_id].name == "neo"

    second = await channel.execute_tool(name="login", arguments={"name": "neo2"})
    assert second.isError
    names = {player.name for player in gateway.rooms.default.world.players.values()}
    assert "neo2" not in names
    await drain()


async def test_provider_serves_gameplay_tools():
    gateway = build_gateway()
    channel = await gateway.create_channel(ttl_seconds=float("inf"))
    session = Session(channel_id=channel.channel_id, mcp_token="m", room=gateway.rooms.default)
    await LocalProvider(channel, session).start()

    names = {tool.name for tool in channel.list_tools()}
    assert {"login", "get_player", "move"} <= names

    # a tool before login is rejected, since the session has no player yet
    before = await channel.execute_tool(name="get_player", arguments={})
    assert before.isError

    await channel.execute_tool(name="login", arguments={"name": "neo"})
    who = await channel.execute_tool(name="get_player", arguments={})
    assert who.structuredContent["name"] == "neo"
    await drain()


async def test_provider_reports_an_unexpected_tool_failure(monkeypatch):
    gateway = build_gateway()
    channel = await gateway.create_channel(ttl_seconds=float("inf"))
    session = Session(channel.channel_id, "m", gateway.rooms.default)
    await LocalProvider(channel, session).start()
    session.adopt(session.room.game.login("neo")["player"]["id"])

    def boom(_player_id):
        raise RuntimeError("boom")

    monkeypatch.setattr(session.room.game, "get_player", boom)
    result = await channel.execute_tool(name="get_player", arguments={})
    assert result.isError
    await drain()


async def test_provider_ignores_non_request_frames():
    gateway = build_gateway()
    channel = await gateway.create_channel(ttl_seconds=float("inf"))
    provider = LocalProvider(channel, Session(channel.channel_id, "m", gateway.rooms.default))
    await provider.start()
    await provider.send_json({"type": "ack"})
    assert provider._tasks == set()
    await drain()


async def test_second_connection_keeps_the_session_alive():
    gateway = build_gateway()
    session = Session("c", "m", gateway.rooms.default)
    gateway._session_connect(session)
    gateway._session_connect(session)
    gateway._session_disconnect(session)
    assert session.connections == 1
    assert session.teardown is None


async def test_teardown_without_a_player_still_removes_the_channel():
    gateway = build_gateway()
    channel = await gateway.create_channel(ttl_seconds=float("inf"))
    session = Session(channel.channel_id, "m", gateway.rooms.default)
    gateway._sessions[channel.channel_id] = session
    await gateway._teardown_after_grace(session)
    assert channel.channel_id not in gateway._sessions
    assert gateway.registry.get(channel.channel_id) is None
    await drain()


async def test_teardown_ignores_a_session_it_no_longer_owns():
    gateway = build_gateway()
    channel = await gateway.create_channel(ttl_seconds=float("inf"))
    orphan = Session(channel.channel_id, "m", gateway.rooms.default)
    # a session that is not the registered owner must not tear down the shared channel
    await gateway._teardown_after_grace(orphan)
    assert gateway.registry.get(channel.channel_id) is not None
    await drain()


async def test_concurrent_same_token_connects_share_one_session():
    gateway = build_gateway()
    first, second = await asyncio.gather(
        gateway._acquire_session(TOKEN), gateway._acquire_session(TOKEN)
    )
    assert first is second
    assert list(gateway._sessions) == [_channel_id_for(TOKEN)]
    await drain()


async def test_serve_cancels_pending_session_teardowns():
    gateway = build_gateway()

    async with gateway.serve():
        with_teardown = Session("c1", "m1", gateway.rooms.default)
        with_teardown.teardown = asyncio.create_task(asyncio.sleep(10))
        gateway._sessions["c1"] = with_teardown
        gateway._sessions["c2"] = Session("c2", "m2", gateway.rooms.default)

    await drain()
    assert with_teardown.teardown.done()


async def test_simulation_survives_a_failing_tick():
    gateway = build_gateway()
    calls = {"n": 0}

    def boom(_dt):
        calls["n"] += 1
        raise RuntimeError("boom")

    gateway.rooms.default.world.tick = boom
    task = asyncio.create_task(gateway._run_simulation(0.001))
    await asyncio.sleep(0.03)
    task.cancel()

    with contextlib.suppress(asyncio.CancelledError):
        await task

    assert calls["n"] > 0
    await drain()
