from __future__ import annotations

import asyncio
import json
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from pydantic import ValidationError
from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.websockets import WebSocket, WebSocketDisconnect

from app.browser_identity import BrowserIdentity, OidcBrowserIdentity
from app.browser_session import BrowserSessionStore
from app.config import AppSettings
from app.gateway import AppGateway
from app.gateway_settings import AppGatewaySettings
from app.oauth_websocket import OAuthWebSocket
from mcpgtw.errors import GatewayConfigurationError
from mcpgtw.oauth.channel_grants import MemoryChannelGrantStore
from mcpgtw.oauth.verified_principal import VerifiedPrincipal

BASE = "https://game.example"
ISSUER = "https://auth.example"
TOKEN = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


class TestIdentity(BrowserIdentity):
    async def authorization_url(self, state, nonce, challenge):
        return (
            ISSUER
            + "/authorize?"
            + urlencode({"state": state, "nonce": nonce, "code_challenge": challenge})
        )

    async def exchange(self, code, verifier, nonce):
        return ISSUER, code


def app_settings(tmp_path, **kwargs):
    return AppSettings(
        **{
            "mcp_auth_mode": "dual",
            "public_base_url": BASE,
            "oidc_issuer": ISSUER,
            "oidc_client_id": "browser",
            "oidc_client_secret": "test-secret",
            "oauth_database_path": str(tmp_path / "oauth.db"),
            "allowed_browser_origins": [BASE],
            "oauth_mcp_client_ids": ["host"],
            "session_grace_seconds": 0.01,
            **kwargs,
        }
    )


def gateway_settings(**kwargs):
    return AppGatewaySettings(
        **{
            "oauth_mode": "resource_server",
            "oauth_resource_url": BASE + "/mcp",
            "oauth_authorization_servers": [ISSUER],
            "oauth_token_verifier": "custom",
            "oauth_allow_static_mcp_tokens": True,
            **kwargs,
        }
    )


def verified(subject):
    return VerifiedPrincipal(
        ISSUER, subject, "host", frozenset({"mcp:access"}), int(time.time()) + 900
    )


@pytest.fixture
async def gateway(tmp_path):
    verifier = AsyncMock()
    verifier.verify.side_effect = lambda token, resource: verified(token)
    gateway = AppGateway(
        app_settings(tmp_path),
        gateway_settings=gateway_settings(),
        browser_identity=TestIdentity(),
        channel_grants=MemoryChannelGrantStore(),
        access_token_verifier=verifier,
    )
    yield gateway

    for session in list(gateway._sessions.values()):
        if session.teardown:
            session.teardown.cancel()

    await gateway.registry.close_all()


def client_for(gateway):
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(gateway.create_app()), base_url=BASE, headers={"Origin": BASE}
    )


async def login(client, subject="alice"):
    response = await client.get("/app/oauth/login")
    assert response.status_code == 307
    query = parse_qs(urlsplit(response.headers["location"]).query)
    assert len(query["code_challenge"][0]) == 43
    response = await client.get(
        "/app/oauth/callback", params={"state": query["state"][0], "code": subject, "iss": ISSUER}
    )
    assert response.status_code == 307
    assert response.headers["location"] == BASE + "/?auth=oauth"
    assert "Secure" in response.headers["set-cookie"]
    return query["state"][0]


def ws_for(cookie, ticket, origin=BASE):
    scope = {
        "type": "websocket",
        "path": "/app/stream",
        "scheme": "wss",
        "server": ("game.example", 443),
        "query_string": urlencode({"ticket": ticket}).encode(),
        "headers": [(b"origin", origin.encode()), (b"cookie", ("game_session=" + cookie).encode())],
    }
    return WebSocket(scope, AsyncMock(), AsyncMock())


async def test_game17_dual_oauth_and_token_isolation(gateway):
    async with client_for(gateway) as client:
        assert (await client.get("/app/info")).json()["authMethods"] == ["token", "oauth"]
        home = await client.get("/")
        assert "script-src 'self'" in home.headers["content-security-policy"]
        assert "connect-src 'self' wss://game.example" in home.headers["content-security-policy"]
        assert "unsafe-eval" not in home.headers["content-security-policy"]
        assert home.headers["referrer-policy"] == "no-referrer"
        state = await login(client)
        assert (await client.post("/app/oauth/ticket")).status_code == 403
        assert (await client.post("/app/oauth/consent")).json() == {"authorized": True}
        ticket = (await client.post("/app/oauth/ticket")).json()["ticket"]
        cookie = client.cookies["game_session"]
        websocket = ws_for(cookie, ticket)
        oauth_session = await gateway.browser_oauth.consume_ticket(websocket, ticket)
        assert oauth_session.auth_method == "oauth"
        message = gateway._session_message(websocket, oauth_session)
        assert "mcpToken" not in message
        assert "mcpToken" not in json.dumps(message)
        token_session = await gateway._acquire_session(TOKEN)
        assert token_session.auth_method == "token"
        assert token_session.mcp_token == "mcp-" + TOKEN
        assert token_session.channel_id != oauth_session.channel_id
        assert gateway._session_message(websocket, token_session)["mcpUrl"].startswith(BASE)
        context = Request(
            {
                "type": "http",
                "path": "/",
                "root_path": "",
                "method": "POST",
                "query_string": b"",
                "headers": [(b"authorization", b"Bearer alice")],
            }
        )
        decision = await gateway.mcp_access_controller.authorize(context)
        assert decision.channel.channel_id == oauth_session.channel_id
        result = await decision.channel.execute_tool(name="login", arguments={"name": "alice"})
        assert not result.is_error
        result = await gateway.registry.get(token_session.channel_id).execute_tool(
            name="login", arguments={"name": "token-player"}
        )
        assert not result.is_error
        assert oauth_session.player_id != token_session.player_id
        assert (
            await client.get(
                "/app/oauth/callback", params={"state": state, "code": "alice", "iss": ISSUER}
            )
        ).status_code == 403
        await gateway.browser_oauth.logout(
            Request(
                {
                    "type": "http",
                    "path": "/",
                    "headers": [
                        (b"origin", BASE.encode()),
                        (b"cookie", ("game_session=" + cookie).encode()),
                    ],
                }
            )
        )
        assert gateway.registry.get(oauth_session.channel_id) is None
        assert gateway.registry.get(token_session.channel_id) is not None
        assert not await gateway.channel_grants.channels(verified("alice"))
        assert (await client.post("/app/oauth/ticket")).status_code == 403
        gateway.browser_oauth.disconnected(websocket, oauth_session.channel_id)
        await gateway.revoke_oauth_channel("unknown")


async def test_game03_04_csrf_ticket_replay_and_cookie_binding(gateway):
    async with client_for(gateway) as client:
        assert (await client.post("/app/oauth/consent")).status_code == 403
        assert (await client.post("/app/oauth/logout")).status_code == 403
        await login(client)
        assert (
            await client.post("/app/oauth/consent", headers={"Origin": "https://evil.example"})
        ).status_code == 403
        await client.post("/app/oauth/consent")
        ticket = (await client.post("/app/oauth/ticket")).json()["ticket"]
        cookie = client.cookies["game_session"]
        assert (
            await gateway.browser_oauth.consume_ticket(
                ws_for(cookie, ticket, "https://evil.example"), ticket
            )
            is None
        )
        winners = await asyncio.gather(
            *(
                gateway.browser_oauth.consume_ticket(ws_for(cookie, ticket), ticket)
                for _ in range(2)
            )
        )
        assert sum(session is not None for session in winners) == 1
        gateway.browser_oauth._sockets.clear()
        ticket = (await client.post("/app/oauth/ticket")).json()["ticket"]
        assert (
            await gateway.browser_oauth.consume_ticket(ws_for("other-cookie", ticket), ticket)
            is None
        )
        assert (
            await gateway.browser_oauth.consume_ticket(ws_for(cookie, "invalid"), "invalid") is None
        )
        browser = await gateway.browser_oauth.store.get("session", cookie)
        await gateway.browser_oauth.store.put(
            "ticket",
            {"cookie": gateway.browser_oauth.store._digest(cookie), "channel": "other"},
            30,
        )
        browser["consented"] = False
        await gateway.browser_oauth.store.update("session", cookie, browser)
        ticket = await gateway.browser_oauth.store.put(
            "ticket",
            {"cookie": gateway.browser_oauth.store._digest(cookie), "channel": browser["channel"]},
            30,
        )
        assert await gateway.browser_oauth.consume_ticket(ws_for(cookie, ticket), ticket) is None
        gateway.browser_oauth.disconnected(ws_for(cookie, ticket), "unknown")


async def test_game05_login_state_callback_and_idp_failures(gateway):
    async with client_for(gateway) as client:
        assert (await client.get("/app/oauth/callback")).status_code == 403
        response = await client.get("/app/oauth/login")
        state = parse_qs(urlsplit(response.headers["location"]).query)["state"][0]
        params = {"state": state, "code": "alice", "iss": ISSUER}
        assert (
            await client.get("/app/oauth/callback", params=params | {"state": "tampered"})
        ).status_code == 403
        assert (
            await client.get("/app/oauth/callback", params=params | {"state": "é"})
        ).status_code == 403
        assert (
            await client.get("/app/oauth/callback", params=params | {"iss": "https://other"})
        ).status_code == 403
        assert (
            await client.get("/app/oauth/callback", params=[*params.items(), ("code", "second")])
        ).status_code == 403
        gateway.browser_oauth.identity.exchange = AsyncMock(side_effect=ValueError("invalid code"))
        assert (await client.get("/app/oauth/callback", params=params)).status_code == 403
        client.cookies.set("game_oauth_state", "expired", domain="game.example", path="/app")
        assert (
            await client.get("/app/oauth/callback", params=params | {"state": "expired"})
        ).status_code == 403
        gateway.browser_oauth.identity.authorization_url = AsyncMock(
            side_effect=ValueError("offline")
        )
        assert (await client.get("/app/oauth/login")).status_code == 403


async def test_game06_account_switch_and_channel_generation(gateway):
    async with client_for(gateway) as client:
        await login(client)
        await client.post("/app/oauth/consent")
        first = next(iter(gateway._sessions.values()))
        pending = first.teardown
        same = await gateway.acquire_oauth_session(ISSUER, "alice")
        assert same is first
        assert same.teardown is pending
        gateway._session_connect(same)
        assert same.teardown is None
        gateway._session_disconnect(same)
        await login(client, "bob")
        assert gateway.registry.get(first.channel_id) is None
        second = next(iter(gateway._sessions.values()))
        gateway.schedule_idle_teardown(second, 100)
        await gateway.revoke_oauth_channel(second.channel_id)
        assert gateway.registry.get(second.channel_id) is None
        assert (await client.post("/app/oauth/consent")).status_code == 403
        gateway.browser_oauth.identity.exchange = AsyncMock(return_value=("https://other", "bob"))
        response = await client.get("/app/oauth/login")
        state = parse_qs(urlsplit(response.headers["location"]).query)["state"][0]
        assert (
            await client.get(
                "/app/oauth/callback", params={"state": state, "code": "bob", "iss": ISSUER}
            )
        ).status_code == 403


async def test_browser_store_expiry_capacity_restart_and_atomic_consume(tmp_path, monkeypatch):
    path = str(tmp_path / "browser.db")
    store = BrowserSessionStore(path, 1)
    secret = await store.put("ticket", {"subject": "alice"}, 30)
    assert (tmp_path / "browser.db").stat().st_mode & 0o077 == 0
    assert (await BrowserSessionStore(path).get("ticket", secret))["subject"] == "alice"

    with pytest.raises(ValueError, match="capacity"):
        await store.put("ticket", {}, 30)

    await store.update("ticket", secret, {"subject": "bob"})
    assert (await store.consume("ticket", secret))["subject"] == "bob"
    assert await store.consume("ticket", secret) is None
    await store.put("ticket", {}, 0)
    assert await store.get("ticket", secret) is None

    for args in [("",), (":memory:",), (path, 0)]:
        with pytest.raises(ValueError):
            BrowserSessionStore(*args)


@pytest.mark.parametrize(
    "changes",
    [
        {"public_base_url": "http://remote.example"},
        {"oidc_client_id": ""},
        {"oauth_database_path": ":memory:"},
        {"oidc_client_secret": ""},
        {"allowed_browser_origins": []},
        {"public_base_url": BASE + "/"},
        {"session_cookie_name": "bad name"},
        {"session_cookie_name": "sessão"},
        {"websocket_ticket_ttl_seconds": 0},
        {"session_idle_seconds": float("inf")},
    ],
)
def test_game01_invalid_app_config(tmp_path, changes):
    with pytest.raises(ValidationError):
        app_settings(tmp_path, **changes)


def test_config_modes_and_cross_validation(tmp_path):
    assert AppSettings().mcp_auth_mode == "legacy"
    assert app_settings(
        tmp_path, oauth_mcp_client_ids="a,b", allowed_browser_origins=BASE
    ).oauth_mcp_client_ids == ["a", "b"]

    for changes in [
        {"oauth_mode": "off"},
        {"oauth_allow_static_mcp_tokens": False},
        {"oauth_resource_url": "https://other/mcp"},
        {"oauth_authorization_servers": ["https://other"]},
    ]:
        with pytest.raises(GatewayConfigurationError):
            AppGateway(app_settings(tmp_path), gateway_settings=gateway_settings(**changes))

    with pytest.raises(GatewayConfigurationError):
        AppGateway(AppSettings(), gateway_settings=gateway_settings())

    with pytest.raises(GatewayConfigurationError):
        AppGateway(
            app_settings(tmp_path, mcp_auth_mode="oauth"), gateway_settings=gateway_settings()
        )

    gateway = AppGateway(
        app_settings(tmp_path, mcp_auth_mode="oauth"),
        gateway_settings=gateway_settings(oauth_allow_static_mcp_tokens=False),
        access_token_verifier=AsyncMock(),
    )
    assert gateway.browser_oauth is not None
    assert isinstance(gateway.browser_oauth.identity, OidcBrowserIdentity)


async def test_game11_hostile_websocket_messages(gateway):
    ws = SimpleNamespace(send_json=AsyncMock())
    session = await gateway._acquire_session(TOKEN)
    await gateway._handle_message(ws, session, "[]")
    await gateway._handle_message(ws, session, "x" * 5000)
    ws.send_json.assert_not_called()
    ws = SimpleNamespace(query_params={"token": TOKEN, "ticket": "ticket"}, close=AsyncMock())
    await gateway.stream_endpoint(ws)
    ws.close.assert_awaited_with(code=1008)
    ws = SimpleNamespace(
        query_params={"ticket": "invalid"},
        cookies={},
        headers=Headers({"origin": BASE}),
        close=AsyncMock(),
    )
    await gateway.stream_endpoint(ws)
    ws.close.assert_awaited_with(code=1008)


async def test_guarded_websocket_stops_after_revocation():
    sent = []
    scope = {"type": "websocket", "path": "/", "headers": [], "query_string": b""}

    async def receive():
        return {"type": "websocket.connect"}

    async def send(message):
        sent.append(message)

    authorized = AsyncMock(return_value=True)
    ws = OAuthWebSocket(WebSocket(scope, receive, send), authorized)
    await ws.accept()
    await ws.send_json({"type": "snapshot"})
    authorized.return_value = False

    with pytest.raises(WebSocketDisconnect):
        await ws.send_json({"type": "private"})

    assert sent[-1]["type"] == "websocket.close"
    assert all("private" not in message.get("text", "") for message in sent)


async def test_oidc_signed_identity_token_and_pkce(tmp_path):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key())) | {
        "kid": "one",
        "alg": "RS256",
    }
    metadata = {
        "issuer": ISSUER,
        "authorization_endpoint": ISSUER + "/authorize",
        "token_endpoint": ISSUER + "/token",
        "jwks_uri": ISSUER + "/keys",
        "code_challenge_methods_supported": ["S256"],
    }
    claims = {
        "iss": ISSUER,
        "aud": "browser",
        "sub": "alice",
        "nonce": "nonce",
        "iat": int(time.time()),
        "exp": int(time.time()) + 900,
    }
    token = jwt.encode(claims, private, algorithm="RS256", headers={"kid": "one"})
    responses = {
        "/.well-known/openid-configuration": metadata,
        "/token": {"id_token": token},
        "/keys": {"keys": [jwk]},
    }

    def handler(request):
        if request.url.path == "/token":
            assert b"code_verifier=verifier" in request.content
            assert request.headers["authorization"].startswith("Basic ")

        return httpx.Response(200, json=responses[request.url.path])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        identity = OidcBrowserIdentity(app_settings(tmp_path), client)
        url = await identity.authorization_url("state", "nonce", "challenge")
        assert "code_challenge_method=S256" in url
        assert await identity.exchange("code", "verifier", "nonce") == (ISSUER, "alice")
        responses["/token"] = {"id_token": "x" * 9000}

        with pytest.raises(ValueError):
            await identity.exchange("code", "verifier", "nonce")

        responses["/token"] = {"id_token": jwt.encode(claims, "x" * 32, algorithm="HS256")}

        with pytest.raises(ValueError):
            await identity.exchange("code", "verifier", "nonce")

        critical_header = jwt.utils.base64url_encode(
            json.dumps(
                {
                    "alg": "RS256",
                    "kid": "one",
                    "crit": ["b64"],
                    "b64": True,
                }
            ).encode()
        ).decode()
        signing_input = critical_header + "." + token.split(".")[1]
        signature = private.sign(signing_input.encode(), padding.PKCS1v15(), hashes.SHA256())
        responses["/token"] = {
            "id_token": signing_input + "." + jwt.utils.base64url_encode(signature).decode()
        }

        with pytest.raises(ValueError, match="algorithm"):
            await identity.exchange("code", "verifier", "nonce")

        responses["/token"] = {"id_token": token}
        responses["/keys"] = {"keys": []}

        with pytest.raises(ValueError):
            await identity.exchange("code", "verifier", "nonce")

        responses["/keys"] = {"keys": "wrong"}

        with pytest.raises(ValueError):
            await identity.exchange("code", "verifier", "nonce")

        responses["/keys"] = {"keys": [jwk]}

        with pytest.raises(ValueError):
            await identity.exchange("code", "verifier", "wrong-nonce")

        identity._metadata = None
        metadata["issuer"] = "https://other"

        with pytest.raises(ValueError):
            await identity.authorization_url("state", "nonce", "challenge")


@pytest.mark.parametrize("handshake_delay", [0, 0.1])
async def test_game08_oauth_stream_with_real_websocket_scope(gateway, handshake_delay):
    async with client_for(gateway) as client:
        await login(client)
        await client.post("/app/oauth/consent")
        ticket = (await client.post("/app/oauth/ticket")).json()["ticket"]
        cookie = client.cookies["game_session"]
        template = ws_for(cookie, ticket)
        queue = asyncio.Queue()
        queue.put_nowait({"type": "websocket.connect"})
        sent = []
        frame_sent = asyncio.Event()

        async def receive():
            message = await queue.get()

            if message["type"] == "websocket.connect":
                await asyncio.sleep(handshake_delay)

            return message

        async def send(message):
            sent.append(message)

            if "text" in message:
                frame_sent.set()

        websocket = WebSocket(template.scope, receive, send)
        task = asyncio.create_task(gateway.stream_endpoint(websocket))

        try:
            await asyncio.wait_for(frame_sent.wait(), timeout=5)
            session_message = next(json.loads(m["text"]) for m in sent if "text" in m)
            assert session_message["authMethod"] == "oauth"
            assert "mcpToken" not in session_message
        finally:
            queue.put_nowait({"type": "websocket.disconnect", "code": 1000})
            await asyncio.wait_for(task, timeout=5)

        session = next(iter(gateway._sessions.values()))
        await session.teardown
        assert gateway.registry.get(session.channel_id) is None


async def test_ticket_cookie_mismatch_missing_channel_and_disconnect_tracking(gateway):
    async with client_for(gateway) as client:
        await login(client)
        await client.post("/app/oauth/consent")
        cookie = client.cookies["game_session"]
        browser = await gateway.browser_oauth.store.get("session", cookie)
        store = gateway.browser_oauth.store
        payload = {"cookie": "other", "channel": browser["channel"]}
        ticket = await store.put("ticket", payload, 30)
        assert await gateway.browser_oauth.consume_ticket(ws_for(cookie, ticket), ticket) is None
        payload["cookie"] = store._digest(cookie)
        payload["channel"] = "other"
        ticket = await store.put("ticket", payload, 30)
        assert await gateway.browser_oauth.consume_ticket(ws_for(cookie, ticket), ticket) is None
        payload["channel"] = browser["channel"]
        session = gateway._sessions.pop(browser["channel"])
        ticket = await store.put("ticket", payload, 30)
        assert await gateway.browser_oauth.consume_ticket(ws_for(cookie, ticket), ticket) is None
        gateway._sessions[session.channel_id] = session
        ticket = await store.put("ticket", payload, 30)
        websocket = ws_for(cookie, ticket)
        assert await gateway.browser_oauth.consume_ticket(websocket, ticket) is session
        gateway.browser_oauth.disconnected(ws_for(cookie, ticket), session.channel_id)
        assert gateway.browser_oauth._sockets[session.channel_id]
        gateway.browser_oauth.disconnected(websocket, session.channel_id)
        assert session.channel_id not in gateway.browser_oauth._sockets
        await login(client)
        assert await gateway.acquire_oauth_session(ISSUER, "alice") is session


async def test_oauth_only_rejects_legacy_socket_and_channel_revoke_branches(tmp_path):
    gateway = AppGateway(
        app_settings(tmp_path, mcp_auth_mode="oauth"),
        gateway_settings=gateway_settings(oauth_allow_static_mcp_tokens=False),
        browser_identity=TestIdentity(),
        access_token_verifier=AsyncMock(),
    )
    ws = SimpleNamespace(query_params={"token": TOKEN}, close=AsyncMock())
    await gateway.stream_endpoint(ws)
    ws.close.assert_awaited_with(code=1008)
    session = await gateway._acquire_session(TOKEN)
    await gateway.revoke_oauth_channel(session.channel_id)
    assert gateway.registry.get(session.channel_id) is not None
    await gateway.registry.close_all()


async def test_game16_browser_endpoint_budgets(gateway):
    from mcpgtw.oauth.rate_limit import WindowOAuthRateLimitPolicy

    gateway.browser_oauth.rate_limit = WindowOAuthRateLimitPolicy(1)

    async with client_for(gateway) as client:
        assert (await client.get("/app/oauth/login")).status_code == 307
        for method, path in [
            ("GET", "/app/oauth/login"),
            ("POST", "/app/oauth/consent"),
            ("GET", "/app/oauth/callback"),
        ]:
            response = await client.request(method, path)
            assert response.status_code == 429
            assert int(response.headers["retry-after"]) >= 1
            assert response.headers["cache-control"] == "no-store"


async def test_owned_browser_http_client_closes_on_shutdown(tmp_path):
    gateway = AppGateway(
        app_settings(tmp_path),
        gateway_settings=gateway_settings(),
        access_token_verifier=AsyncMock(),
    )
    client = gateway._owned_browser_identity.client

    async with gateway.lifespan(gateway.create_app()):
        assert not client.is_closed

    assert client.is_closed


async def test_ambiguous_browser_cookies_fail_closed(gateway):
    from app.browser_cookie import browser_cookie

    for header in ["other=value", "game_session=one; game_session=two", "x" * 8193]:
        request = Request({"type": "http", "headers": [(b"cookie", header.encode())]})
        assert browser_cookie(request, "game_session") == ""

    async with client_for(gateway) as client:
        await login(client)
        await client.post("/app/oauth/consent")
        cookie = client.cookies["game_session"]
        duplicate = {"Cookie": "game_session=" + cookie + "; game_session=attacker"}
        assert (await client.post("/app/oauth/ticket", headers=duplicate)).status_code == 403
        assert (await client.post("/app/oauth/logout", headers=duplicate)).status_code == 403
        ticket = (await client.post("/app/oauth/ticket")).json()["ticket"]
        scope = ws_for(cookie, ticket).scope
        scope["headers"].append((b"cookie", b"game_session=attacker"))
        assert (
            await gateway.browser_oauth.consume_ticket(
                WebSocket(scope, AsyncMock(), AsyncMock()), ticket
            )
            is None
        )


async def test_browser_storage_capacity_returns_safe_denial(gateway):
    async with client_for(gateway) as client:
        gateway.browser_oauth.store.maximum_records = 1
        assert (await client.get("/app/oauth/login")).status_code == 307
        assert (await client.get("/app/oauth/login")).status_code == 403
        gateway.browser_oauth.store.maximum_records = 10000
        await login(client)
        await client.post("/app/oauth/consent")
        gateway.browser_oauth.store.put = AsyncMock(side_effect=ValueError("capacity"))
        response = await client.post("/app/oauth/ticket")
        assert response.status_code == 403
        assert "capacity" not in response.text


def test_invalid_configuration_does_not_render_browser_secret(tmp_path):
    secret = "do-not-render-browser-credential"

    with pytest.raises(ValidationError) as error:
        app_settings(tmp_path, oidc_client_secret=secret, oauth_database_path="")

    assert secret not in str(error.value)


def test_external_oauth_requires_approved_clients(tmp_path):
    with pytest.raises(GatewayConfigurationError, match="approved MCP"):
        AppGateway(
            app_settings(tmp_path, oauth_mcp_client_ids=[]), gateway_settings=gateway_settings()
        )


async def test_game16_verified_account_budget_survives_address_rotation(gateway):
    from mcpgtw.oauth.rate_limit import WindowOAuthRateLimitPolicy

    async with client_for(gateway) as client:
        await login(client)
        gateway.browser_oauth.principal_limit = WindowOAuthRateLimitPolicy(1, 60)
        assert (await client.post("/app/oauth/consent")).status_code == 200
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(gateway.create_app(), client=("203.0.113.20", 123)),
            base_url=BASE,
            cookies=client.cookies,
            headers={"Origin": BASE},
        ) as other:
            response = await other.post("/app/oauth/ticket")

        assert response.status_code == 429
        assert int(response.headers["retry-after"]) >= 1
        assert (await gateway._acquire_session(TOKEN)).auth_method == "token"


async def test_browser_budget_class_and_instance_injection(gateway):
    from app.browser_oauth import BrowserOAuth
    from mcpgtw.oauth.rate_limit import WindowOAuthRateLimitPolicy

    class CustomPolicy(WindowOAuthRateLimitPolicy):
        pass

    class CustomBrowser(BrowserOAuth):
        rate_limit_class = CustomPolicy

    browser = gateway.browser_oauth
    custom = CustomBrowser(gateway, browser.identity, browser.store)
    assert isinstance(custom.rate_limit, CustomPolicy)
    assert isinstance(custom.principal_limit, CustomPolicy)
    injected = WindowOAuthRateLimitPolicy(3, 4, 5)
    custom = BrowserOAuth(
        gateway, browser.identity, browser.store, rate_limit=injected, principal_limit=injected
    )
    assert custom.rate_limit is injected and custom.principal_limit is injected


async def test_game10_same_account_clients_keep_distinct_granted_scopes(gateway):
    from dataclasses import replace

    async with client_for(gateway) as client:
        await login(client)
        await client.post("/app/oauth/consent")
        channel = next(iter(gateway._sessions))
        reader = verified("alice")
        writer = replace(reader, client_id="writer", scopes=reader.scopes | {"game:write"})
        await gateway.channel_grants.grant(writer, channel)
        assert await gateway.channel_grants.channels(reader) == frozenset({channel})
        assert await gateway.channel_grants.channels(writer) == frozenset({channel})
        assert not await gateway.channel_grants.channels(replace(reader, scopes=writer.scopes))
        assert not await gateway.channel_grants.channels(replace(writer, subject="bob"))
        await gateway.channel_grants.revoke(writer, channel)
        assert not await gateway.channel_grants.channels(writer)
        assert await gateway.channel_grants.channels(reader) == frozenset({channel})
        assert (await client.post("/app/oauth/logout")).status_code == 200
        assert not await gateway.channel_grants.channels(reader)


async def test_game05_storage_failure_after_verified_callback_does_not_create_owner(gateway):
    async with client_for(gateway) as client:
        response = await client.get("/app/oauth/login")
        state = parse_qs(urlsplit(response.headers["location"]).query)["state"][0]
        gateway.acquire_oauth_session = AsyncMock(side_effect=ValueError("capacity exceeded"))
        response = await client.get(
            "/app/oauth/callback", params={"state": state, "code": "alice", "iss": ISSUER}
        )
        assert response.status_code == 403
        assert not gateway._oauth_owners
        assert not gateway._sessions
        assert "game_session" not in client.cookies


@pytest.mark.parametrize("elapsed, expected", [(180, 307), (599, 307), (600, 403), (601, 403)])
async def test_browser_login_wait_and_expired_state_replay(gateway, monkeypatch, elapsed, expected):
    clock = [time.time()]
    monkeypatch.setattr(time, "time", lambda: clock[0])
    identity = gateway.browser_oauth.identity
    identity.exchange = AsyncMock(return_value=(ISSUER, "alice"))

    async with client_for(gateway) as client:
        response = await client.get("/app/oauth/login")
        state = parse_qs(urlsplit(response.headers["location"]).query)["state"][0]
        assert "Max-Age=600" in response.headers["set-cookie"]
        clock[0] += elapsed
        response = await client.get(
            "/app/oauth/callback",
            params={"state": state, "code": "alice", "iss": ISSUER},
            headers={"cookie": "game_oauth_state=" + state},
        )
        assert response.status_code == expected
        assert await gateway.browser_oauth.store.get("login", state) is None

        if expected == 403:
            identity.exchange.assert_not_awaited()
            assert not gateway._sessions
        else:
            identity.exchange.assert_awaited_once()
            assert len(gateway._sessions) == 1


@pytest.mark.parametrize("timeout", [0, -1, 1801])
def test_browser_login_timeout_rejects_invalid_values(timeout):
    with pytest.raises(ValidationError):
        AppSettings(oauth_login_timeout_seconds=timeout)


async def test_browser_resume_checks_consent_origin_expiry_and_never_renews_grants(gateway):
    async with client_for(gateway) as client:
        assert (await client.post("/app/oauth/session")).status_code == 403
        await login(client)
        assert (await client.post("/app/oauth/session")).status_code == 403
        await client.post("/app/oauth/consent")
        cookie = client.cookies["game_session"]
        browser = await gateway.browser_oauth.store.get("session", cookie)
        assert (await client.post("/app/oauth/session")).json() == {"authorized": True}
        assert await gateway.browser_oauth.store.get("session", cookie) == browser
        assert (
            await client.post("/app/oauth/session", headers={"Origin": "https://evil.example"})
        ).status_code == 403
        await gateway.channel_grants.revoke(verified("alice"), browser["channel"])
        await client.post("/app/oauth/session")
        assert not await gateway.channel_grants.channels(verified("alice"))
        await gateway.browser_oauth.store.consume("session", cookie)
        assert (await client.post("/app/oauth/session")).status_code == 403


async def test_same_account_reauthentication_preserves_cookie_player_and_other_tabs(gateway):
    async with client_for(gateway) as client:
        await login(client)
        await client.post("/app/oauth/consent")
        cookie = client.cookies["game_session"]
        browser = await gateway.browser_oauth.store.get("session", cookie)
        session = gateway._sessions[browser["channel"]]
        channel = gateway.registry.get(session.channel_id)
        await channel.execute_tool(name="login", arguments={"name": "shared"})
        player_id = session.player_id
        first_ticket = (await client.post("/app/oauth/ticket")).json()["ticket"]
        first = ws_for(cookie, first_ticket)
        assert await gateway.browser_oauth.consume_ticket(first, first_ticket) is session
        await login(client)
        assert client.cookies["game_session"] == cookie
        assert await gateway.browser_oauth.store.get("session", cookie) == browser
        second_ticket = (await client.post("/app/oauth/ticket")).json()["ticket"]
        second = ws_for(cookie, second_ticket)
        assert await gateway.browser_oauth.consume_ticket(second, second_ticket) is session
        assert gateway.browser_oauth._sockets[session.channel_id] == {first, second}
        assert session.player_id == player_id
        session.oauth_authorized_until = browser["expires_at"] + 60
        await client.post("/app/oauth/consent")
        assert session.oauth_authorized_until == browser["expires_at"] + 60
        await client.post("/app/oauth/logout")
        assert (await client.post("/app/oauth/session")).status_code == 403
        assert gateway.registry.get(session.channel_id) is None
