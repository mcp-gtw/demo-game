from __future__ import annotations

import base64
import hashlib
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from test_oauth_gateway import BASE, app_settings, gateway_settings

from app.embedded_browser_identity import EmbeddedBrowserIdentity
from app.game_consent_policy import GameConsentPolicy
from app.gateway import AppGateway

VERIFIER = "a" * 64
CHALLENGE = (
    base64.urlsafe_b64encode(hashlib.sha256(VERIFIER.encode()).digest()).rstrip(b"=").decode()
)
REDIRECT = "https://host.example/callback"


@pytest.fixture
async def embedded(tmp_path):
    gateway = AppGateway(
        app_settings(
            tmp_path,
            oidc_issuer=BASE,
            oauth_account_registration_enabled=True,
            oauth_mcp_client_ids=[],
        ),
        gateway_settings=gateway_settings(
            oauth_mode="embedded",
            oauth_token_verifier="jwt",
            oauth_jwks_url=BASE + "/oauth/jwks",
            oauth_authorization_servers=[BASE],
            oauth_embedded_dcr_enabled=True,
        ),
    )

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(gateway.create_app()), base_url=BASE, headers={"Origin": BASE}
    ) as client:
        yield gateway, client

    for session in list(gateway._sessions.values()):
        if session.teardown:
            session.teardown.cancel()

    await gateway.registry.close_all()


async def test_public_oauth_endpoint_is_available_before_login_without_creating_channels(embedded):
    gateway, client = embedded
    response = await client.get(
        "/app/info", headers={"Host": "evil.example", "X-Forwarded-Host": "evil.example"}
    )
    assert response.status_code == 200
    assert response.json()["oauthMcpUrl"] == BASE + "/mcp"
    assert "set-cookie" not in response.headers
    assert not gateway._sessions
    assert not gateway._oauth_owners
    request = client.build_request("GET", "/mcp")
    del request.headers["origin"]
    response = await client.send(request)
    assert response.status_code == 401
    assert "resource_metadata=" in response.headers["www-authenticate"]
    assert not gateway._sessions


async def browser_login(client):
    start = await client.get("/app/oauth/login")
    assert start.status_code == 307
    authorize = await client.get(start.headers["location"])
    assert authorize.status_code == 303
    assert (await client.get("/oauth/login")).status_code == 200
    response = await client.post(
        "/oauth/login",
        data={
            "username": "alice",
            "password": "strong-local-password",
            "csrf": client.cookies["oauth_csrf"],
            "action": "register",
        },
    )
    assert response.status_code == 303
    await client.get("/oauth/consent")
    response = await client.post(
        "/oauth/consent", data={"csrf": client.cookies["oauth_csrf"], "action": "allow"}
    )
    assert response.status_code == 303
    assert (await client.get(response.headers["location"])).status_code == 307
    assert (await client.post("/app/oauth/consent")).status_code == 200


async def host_code(client, client_id):
    authorize = await client.get(
        "/oauth/authorize",
        params={
            "client_id": client_id,
            "redirect_uri": REDIRECT,
            "response_type": "code",
            "code_challenge_method": "S256",
            "code_challenge": CHALLENGE,
            "resource": BASE + "/mcp",
            "scope": "mcp:access",
            "state": "state",
        },
    )
    assert authorize.status_code == 303
    await client.get("/oauth/consent")
    response = await client.post(
        "/oauth/consent", data={"csrf": client.cookies["oauth_csrf"], "action": "allow"}
    )
    return parse_qs(urlsplit(response.headers["location"]).query)["code"][0]


async def test_embedded_game_real_account_dcr_pkce_refresh_logout_and_token(embedded):
    gateway, client = embedded
    await browser_login(client)
    registered = (
        await client.post(
            "/oauth/register", json={"redirect_uris": [REDIRECT], "client_name": "Local MCP host"}
        )
    ).json()
    code = await host_code(client, registered["client_id"])
    result = await client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": registered["client_id"],
            "redirect_uri": REDIRECT,
            "code": code,
            "code_verifier": VERIFIER,
            "resource": BASE + "/mcp",
        },
    )
    assert result.status_code == 200
    tokens = result.json()
    server = gateway.authorization_server
    principal = await server.verify(tokens["access_token"], BASE + "/mcp")
    assert principal is not None
    session = next(iter(gateway._sessions.values()))

    assert session.channel_id in await gateway.channel_grants.channels(principal)
    ticket = await client.post("/app/oauth/ticket")
    assert ticket.status_code == 200
    policy = GameConsentPolicy(gateway)
    assert not await policy.validate(
        "unknown", principal.client_id, BASE + "/mcp", principal.scopes
    )
    assert not await policy.approve(
        principal.subject, principal.client_id, "wrong", principal.scopes
    )
    assert not await policy.approve(
        principal.subject, principal.client_id, BASE + "/mcp", frozenset({"admin"})
    )
    refresh = await client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": principal.client_id,
            "refresh_token": tokens["refresh_token"],
            "resource": BASE + "/mcp",
        },
    )
    assert refresh.status_code == 200
    legacy = await gateway._acquire_session("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    assert legacy
    assert (await client.post("/app/oauth/logout")).status_code == 200
    assert await server.verify(tokens["access_token"], BASE + "/mcp") is None
    assert gateway.registry.get(legacy.channel_id) is not None
    assert not await policy.validate(
        principal.subject, principal.client_id, BASE + "/mcp", principal.scopes
    )
    assert "oauth_login" not in client.cookies


async def test_embedded_browser_exchange_failures(embedded):
    gateway, client = embedded
    identity = gateway.browser_oauth.identity
    assert isinstance(identity, EmbeddedBrowserIdentity)
    with pytest.raises(ValueError):
        await identity.exchange("missing", VERIFIER, "nonce")
    browser = gateway.authorization_server.clients.pre_registered.pop("browser")
    with pytest.raises(ValueError):
        await identity.exchange("missing", VERIFIER, "nonce")
    gateway.authorization_server.clients.pre_registered["browser"] = {**browser, "secret": "wrong"}
    with pytest.raises(ValueError):
        await identity.exchange("missing", VERIFIER, "nonce")
    gateway.authorization_server.clients.pre_registered["browser"] = browser
    await browser_login(client)
    start = await client.get("/app/oauth/login")
    await client.get(start.headers["location"])
    await client.get("/oauth/consent")
    response = await client.post(
        "/oauth/consent", data={"csrf": client.cookies["oauth_csrf"], "action": "allow"}
    )
    code = parse_qs(urlsplit(response.headers["location"]).query)["code"][0]
    state = parse_qs(urlsplit(response.headers["location"]).query)["state"][0]
    transaction = await gateway.browser_oauth.store.get("login", state)
    with pytest.raises(ValueError, match="nonce"):
        await identity.exchange(code, transaction["verifier"], "wrong-nonce")


async def test_embedded_channel_expiry_and_revocation(embedded):
    gateway, client = embedded
    await browser_login(client)
    owner = next(iter(gateway._oauth_owners))
    session = next(iter(gateway._sessions.values()))
    session.oauth_authorized_until = int(time.time()) - 1
    assert not await GameConsentPolicy(gateway).validate(
        owner[1], "host", BASE + "/mcp", frozenset({"mcp:access"})
    )
    other = await gateway.acquire_oauth_session(BASE, "bob")
    await gateway.registry.remove_channel(other.channel_id)
    await gateway.registry.remove_channel(session.channel_id)


@pytest.mark.parametrize("removed", ["client", "scope"])
async def test_game10_refresh_cannot_recreate_revoked_consent_or_scopes(embedded, removed):
    from dataclasses import replace
    from unittest.mock import AsyncMock

    gateway, client = embedded
    await browser_login(client)
    registered = (await client.post("/oauth/register", json={"redirect_uris": [REDIRECT]})).json()
    client_id = registered["client_id"]
    code = await host_code(client, client_id)
    response = await client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "redirect_uri": REDIRECT,
            "code": code,
            "code_verifier": VERIFIER,
            "resource": BASE + "/mcp",
        },
    )
    assert response.status_code == 200
    tokens = response.json()
    server = gateway.authorization_server
    principal = await server.verify(tokens["access_token"], BASE + "/mcp")
    channel = next(iter(gateway._sessions))
    if removed == "client":
        await gateway.channel_grants.revoke(principal, channel)
    else:
        await gateway.channel_grants.grant(replace(principal, scopes=frozenset()), channel)

    server.consent.approve = AsyncMock(wraps=server.consent.approve)
    response = await client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": tokens["refresh_token"],
            "resource": BASE + "/mcp",
        },
    )
    assert response.status_code == 400
    assert not await gateway.channel_grants.channels(principal)
    assert await server.verify(tokens["access_token"], BASE + "/mcp") is None
    server.consent.approve.assert_not_awaited()


async def host_first_login(client, username, *, action="allow", csrf=None):
    registered = (await client.post("/oauth/register", json={"redirect_uris": [REDIRECT]})).json()
    client_id = registered["client_id"]
    authorize = await client.get(
        "/oauth/authorize",
        params={
            "client_id": client_id,
            "redirect_uri": REDIRECT,
            "response_type": "code",
            "code_challenge_method": "S256",
            "code_challenge": CHALLENGE,
            "resource": BASE + "/mcp",
            "scope": "mcp:access",
            "state": "client-first-state",
        },
    )
    assert authorize.status_code == 303
    assert urlsplit(authorize.headers["location"]).path == "/oauth/login"
    assert (await client.get("/oauth/login")).status_code == 200
    response = await client.post(
        "/oauth/login",
        data={
            "username": username,
            "password": "strong-local-password",
            "csrf": client.cookies["oauth_csrf"],
            "action": "register",
        },
    )
    assert response.status_code == 303
    assert (await client.get("/oauth/consent")).status_code == 200
    response = await client.post(
        "/oauth/consent",
        data={"csrf": client.cookies["oauth_csrf"] if csrf is None else csrf, "action": action},
    )
    return client_id, response


async def exchange_host_code(client, client_id, response):
    params = parse_qs(urlsplit(response.headers["location"]).query)
    assert params["state"] == ["client-first-state"]
    response = await client.post(
        "/oauth/token",
        data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "redirect_uri": REDIRECT,
            "code": params["code"][0],
            "code_verifier": VERIFIER,
            "resource": BASE + "/mcp",
        },
    )
    assert response.status_code == 200
    return response.json()


async def test_host_first_creates_owned_channel_and_later_browser_reuses_player(embedded):
    gateway, client = embedded
    assert not gateway._sessions
    client_id, response = await host_first_login(client, "alice")
    assert response.status_code == 303
    assert "game_session" not in client.cookies
    tokens = await exchange_host_code(client, client_id, response)
    principal = await gateway.authorization_server.verify(tokens["access_token"], BASE + "/mcp")
    owned = next(iter(gateway._sessions.values()))
    assert owned.auth_method == "oauth"
    assert owned.connections == 0
    assert owned.teardown is not None
    assert gateway._oauth_owners[(BASE, principal.subject)] == owned.channel_id
    assert await gateway.channel_grants.channels(principal) == {owned.channel_id}
    assert (
        await gateway.mcp_access_controller.oauth_access.channel_access.resolve(principal, "")
        == owned.channel_id
    )
    channel = gateway.registry.get(owned.channel_id)
    login = await channel.execute_tool(
        name="login", arguments={"name": "MCP-first", "class": "warrior"}
    )
    assert not login.is_error
    player_id = owned.player_id
    assert player_id in owned.room.world.players
    start = await client.get("/app/oauth/login")
    response = await client.get(start.headers["location"])
    assert urlsplit(response.headers["location"]).path == "/oauth/consent"
    await client.get("/oauth/consent")
    response = await client.post(
        "/oauth/consent", data={"csrf": client.cookies["oauth_csrf"], "action": "allow"}
    )
    assert (await client.get(response.headers["location"])).status_code == 307
    assert (await client.post("/app/oauth/consent")).status_code == 200
    assert len(gateway._sessions) == 1
    assert gateway._sessions[owned.channel_id] is owned
    assert owned.player_id == player_id
    assert (await client.post("/app/oauth/ticket")).status_code == 200


@pytest.mark.parametrize("action,csrf,status", [("deny", None, 303), ("allow", "forged", 403)])
async def test_host_first_denial_or_forged_consent_cannot_create_channel(
    embedded, action, csrf, status
):
    gateway, client = embedded
    _, response = await host_first_login(client, "alice", action=action, csrf=csrf)
    assert response.status_code == status
    assert not gateway._sessions
    assert not gateway._oauth_owners


async def test_host_first_accounts_cannot_address_each_others_channel(embedded):
    gateway, first = embedded
    client_id, response = await host_first_login(first, "alice")
    tokens = await exchange_host_code(first, client_id, response)
    alice = await gateway.authorization_server.verify(tokens["access_token"], BASE + "/mcp")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(gateway.create_app()), base_url=BASE, headers={"Origin": BASE}
    ) as second:
        client_id, response = await host_first_login(second, "bob")
        tokens = await exchange_host_code(second, client_id, response)
        bob = await gateway.authorization_server.verify(tokens["access_token"], BASE + "/mcp")
    policy = gateway.mcp_access_controller.oauth_access.channel_access
    alice_channel = await policy.resolve(alice, "")
    bob_channel = await policy.resolve(bob, "")
    assert alice_channel != bob_channel
    assert await policy.resolve(bob, alice_channel) is None
    assert await policy.resolve(alice, bob_channel) is None


async def test_host_only_expiry_revokes_grants_tokens_and_player(embedded):
    gateway, client = embedded
    client_id, response = await host_first_login(client, "alice")
    tokens = await exchange_host_code(client, client_id, response)
    server = gateway.authorization_server
    principal = await server.verify(tokens["access_token"], BASE + "/mcp")
    owned = next(iter(gateway._sessions.values()))
    channel = gateway.registry.get(owned.channel_id)
    await channel.execute_tool(name="login", arguments={"name": "Transient"})
    owned.last_mcp_activity = time.monotonic() - gateway.app_settings.session_idle_seconds
    gateway.schedule_idle_teardown(owned, 0)
    await owned.teardown
    assert not gateway._sessions
    assert not gateway._oauth_owners
    assert not owned.room.world.players
    assert not await gateway.channel_grants.channels(principal)
    assert await server.verify(tokens["access_token"], BASE + "/mcp") is None
    response = await client.post(
        "/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": tokens["refresh_token"],
            "resource": BASE + "/mcp",
        },
    )
    assert response.status_code == 400
    assert not gateway._sessions


async def test_host_first_capacity_denies_without_creating_unbounded_sessions(embedded):
    gateway, client = embedded
    gateway.settings.maximum_channels = 1
    await host_first_login(client, "alice")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(gateway.create_app()), base_url=BASE, headers={"Origin": BASE}
    ) as second:
        _, response = await host_first_login(second, "bob")
    assert response.status_code == 303
    assert parse_qs(urlsplit(response.headers["location"]).query)["error"] == ["access_denied"]
    assert len(gateway._sessions) == len(gateway._oauth_owners) == 1


async def test_explicit_reconsent_renews_expired_grant_but_validation_does_not(embedded):
    gateway, client = embedded
    await browser_login(client)
    owner = next(iter(gateway._oauth_owners))
    session = next(iter(gateway._sessions.values()))
    session.oauth_authorized_until = int(time.time()) - 1
    policy = GameConsentPolicy(gateway)
    scopes = frozenset({"mcp:access"})
    assert not await policy.validate(owner[1], "host", BASE + "/mcp", scopes)
    assert session.oauth_authorized_until < time.time()
    assert await policy.approve(owner[1], "host", BASE + "/mcp", scopes)
    assert session.oauth_authorized_until > time.time()
    assert await policy.validate(owner[1], "host", BASE + "/mcp", scopes)


async def test_idle_timer_cannot_remove_a_connected_session(embedded):
    gateway, _ = embedded
    session = await gateway.acquire_oauth_session(BASE, "alice")
    gateway._session_connect(session)
    assert session.teardown is None
    gateway.schedule_idle_teardown(session, 0)
    await session.teardown
    assert gateway._sessions[session.channel_id] is session
    gateway._session_disconnect(session)
    await session.teardown
    assert not gateway._sessions


async def test_signout_removes_connected_oauth_without_touching_token_session(embedded):
    gateway, client = embedded
    client_id, response = await host_first_login(client, "alice")
    tokens = await exchange_host_code(client, client_id, response)
    owned = next(iter(gateway._sessions.values()))
    gateway._session_connect(owned)
    assert owned.teardown is None
    await gateway.revoke_oauth_channel(owned.channel_id)
    assert not gateway._sessions
    assert await gateway.authorization_server.verify(tokens["access_token"], BASE + "/mcp") is None
    token = await gateway._acquire_session("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    await gateway.revoke_oauth_channel(token.channel_id)
    assert gateway._sessions[token.channel_id] is token
    assert gateway.registry.get(token.channel_id) is not None
