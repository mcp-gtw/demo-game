import asyncio
import base64
import hashlib
import json
import re
import secrets
import ssl
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit

import httpx
import httpx2
import websockets
from gameplay import move_player
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client


def docker(*args):
    return subprocess.check_output(["docker", *args], text=True, stderr=subprocess.STDOUT).strip()


async def client_check():
    ctx = ssl._create_unverified_context()
    async with websockets.connect(
        "wss://localhost:19490/app/stream?token=" + str(uuid.uuid4()),
        ssl=ctx,
        origin="https://mcpgame.paulox.dev",
    ) as socket:
        session = json.loads(await socket.recv())
        assert session["mcpUrl"].startswith("https://mcpgame.paulox.dev/mcp/")
        path = httpx.URL(session["mcpUrl"]).path
        async with (
            httpx2.AsyncClient(
                verify=False, headers={"Authorization": "Bearer " + session["mcpToken"]}
            ) as client,
            streamable_http_client("https://localhost:19490" + path, http_client=client) as (
                read,
                write,
            ),
            ClientSession(read, write) as mcp,
        ):
            await mcp.initialize()
            assert len((await mcp.list_tools()).tools) == 10


async def oauth_check(host_first=False):
    base = "https://localhost:19490"
    issuer = "https://mcpgame.paulox.dev"
    resource = issuer + "/mcp"

    def redirect(response):
        target = urlsplit(response.headers["location"])
        assert target.scheme + "://" + target.netloc == issuer
        return target.path + ("?" + target.query if target.query else "")

    async with httpx.AsyncClient(
        base_url=base, verify=False, trust_env=False, headers={"Origin": issuer}
    ) as client:
        if not host_first:
            response = await client.get("/app/oauth/login")
            response = await client.get(redirect(response))
            assert redirect(response) == "/oauth/login"
            await client.get("/oauth/login")
            response = await client.post(
                "/oauth/login",
                data={
                    "username": "proxy-" + secrets.token_hex(4),
                    "password": secrets.token_urlsafe(24),
                    "action": "register",
                    "csrf": client.cookies["oauth_csrf"],
                },
            )
            assert response.status_code == 303
            await client.get(redirect(response))
            response = await client.post(
                "/oauth/consent", data={"action": "allow", "csrf": client.cookies["oauth_csrf"]}
            )
            assert (await client.get(redirect(response))).status_code == 307
            assert (await client.post("/app/oauth/consent")).status_code == 200
        registered = (
            await client.post(
                "/oauth/register", json={"redirect_uris": ["https://client.example/callback"]}
            )
        ).json()
        verifier = "a" * 64
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        response = await client.get(
            "/oauth/authorize",
            params={
                "response_type": "code",
                "client_id": registered["client_id"],
                "redirect_uri": "https://client.example/callback",
                "scope": "mcp:access",
                "resource": resource,
                "state": "proxy-state",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            },
        )
        if host_first:
            assert redirect(response) == "/oauth/login"
            await client.get("/oauth/login")
            response = await client.post(
                "/oauth/login",
                data={
                    "username": "host-first-" + secrets.token_hex(4),
                    "password": secrets.token_urlsafe(24),
                    "action": "register",
                    "csrf": client.cookies["oauth_csrf"],
                },
            )
            assert response.status_code == 303
            assert "game_session" not in client.cookies

        await client.get(redirect(response))
        response = await client.post(
            "/oauth/consent", data={"action": "allow", "csrf": client.cookies["oauth_csrf"]}
        )
        query = parse_qs(urlsplit(response.headers["location"]).query)
        assert query["state"] == ["proxy-state"] and query["iss"] == [issuer]
        token_request = {
            "grant_type": "authorization_code",
            "client_id": registered["client_id"],
            "redirect_uri": "https://client.example/callback",
            "code": query["code"][0],
            "code_verifier": verifier,
            "resource": resource,
        }
        response = await client.post("/oauth/token", data=token_request)
        assert response.status_code == 200
        access = response.json()["access_token"]
        assert (await client.post("/oauth/token", data=token_request)).status_code == 400

        if host_first:
            async with (
                httpx2.AsyncClient(
                    verify=False, headers={"Authorization": "Bearer " + access}
                ) as transport,
                streamable_http_client(base + "/mcp", http_client=transport) as (read, write),
                ClientSession(read, write) as mcp,
            ):
                await mcp.discover()
                assert len((await mcp.list_tools()).tools) == 10
                assert not (await mcp.call_tool("login", {"name": "ProxyHostFirst"})).is_error
                player = (await mcp.call_tool("get_player", {})).structured_content
                assert await move_player(mcp)

            response = await client.get("/app/oauth/login")
            response = await client.get(redirect(response))
            assert redirect(response) == "/oauth/consent"
            await client.get("/oauth/consent")
            response = await client.post(
                "/oauth/consent", data={"action": "allow", "csrf": client.cookies["oauth_csrf"]}
            )
            assert (await client.get(redirect(response))).status_code == 307
            assert (await client.post("/app/oauth/consent")).status_code == 200

        ticket = (await client.post("/app/oauth/ticket")).json()["ticket"]
        cookies = {cookie.name: cookie.value for cookie in client.cookies.jar}
        async with websockets.connect(
            "wss://localhost:19490/app/stream?" + urlencode({"ticket": ticket}),
            ssl=ssl._create_unverified_context(),
            origin=issuer,
            additional_headers={"Cookie": "game_session=" + cookies["game_session"]},
        ) as socket:
            browser = json.loads(await socket.recv())
            assert "mcpToken" not in browser
            path = urlsplit(browser["mcpUrl"]).path
            async with (
                httpx2.AsyncClient(
                    verify=False, headers={"Authorization": "Bearer " + access}
                ) as transport,
                streamable_http_client(base + path, http_client=transport) as (read, write),
                ClientSession(read, write) as mcp,
            ):
                await mcp.initialize()
                assert len((await mcp.list_tools()).tools) == 10
                if host_first:
                    assert (await mcp.call_tool("get_player", {})).structured_content[
                        "id"
                    ] == player["id"]
                    assert json.loads(await socket.recv())["player"]["id"] == player["id"]
                else:
                    assert not (
                        await mcp.call_tool("login", {"name": "ProxyOAuth", "class": "warrior"})
                    ).is_error
                assert not (await mcp.call_tool("get_player", {})).is_error
                assert await move_player(mcp)
            assert (await client.post("/app/oauth/logout")).status_code == 200
            assert (
                await client.post(path, headers={"Authorization": "Bearer " + access})
            ).status_code == 401


nonce = secrets.token_hex(6)
network = "oauth-test-" + nonce
volume = "oauth-data-" + nonce
app = "oauth-game-" + nonce
proxy = "oauth-proxy-" + nonce
created = []
with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    subprocess.run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "1",
            "-subj",
            "/CN=localhost",
            "-keyout",
            str(root / "key.pem"),
            "-out",
            str(root / "cert.pem"),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    config = (Path(__file__).resolve().parents[2] / "nginx.conf").read_text()
    config = config.replace(
        "listen 80;",
        "listen 443 ssl;\n"
        "        ssl_certificate /cert/cert.pem;\n"
        "        ssl_certificate_key /cert/key.pem;",
    ).replace("$http_x_forwarded_proto", "$scheme")
    (root / "nginx.conf").write_text(config)
    env = dict(
        APP_MCP_AUTH_MODE="dual",
        APP_PUBLIC_BASE_URL="https://mcpgame.paulox.dev",
        APP_OIDC_ISSUER="https://mcpgame.paulox.dev",
        APP_OIDC_CLIENT_ID="browser",
        APP_OIDC_CLIENT_SECRET=secrets.token_urlsafe(32),
        APP_OAUTH_DATABASE_PATH="/data/oauth.sqlite",
        APP_OAUTH_ACCOUNT_REGISTRATION_ENABLED="true",
        APP_ALLOWED_BROWSER_ORIGINS="https://mcpgame.paulox.dev",
        APP_OAUTH_MCP_CLIENT_IDS="host",
        GATEWAY_OAUTH_MODE="embedded",
        GATEWAY_OAUTH_EMBEDDED_DCR_ENABLED="true",
        GATEWAY_OAUTH_RESOURCE_URL="https://mcpgame.paulox.dev/mcp",
        GATEWAY_OAUTH_AUTHORIZATION_SERVERS="https://mcpgame.paulox.dev",
        GATEWAY_OAUTH_JWKS_URL="https://mcpgame.paulox.dev/oauth/jwks",
        GATEWAY_OAUTH_ALLOW_STATIC_MCP_TOKENS="true",
        GATEWAY_ALLOWED_MCP_ORIGINS="https://mcpgame.paulox.dev",
        GATEWAY_CORS_ALLOW_ORIGINS="https://mcpgame.paulox.dev",
    )
    (root / "env").write_text("\n".join(k + "=" + v for k, v in env.items()) + "\n")
    (root / "env").chmod(0o600)
    try:
        docker("network", "create", network)
        docker("volume", "create", volume)
        docker(
            "run",
            "-d",
            "--rm",
            "--network",
            network,
            "--network-alias",
            "app",
            "--name",
            app,
            "--env-file",
            str(root / "env"),
            "-v",
            volume + ":/data",
            "mcp-gtw-game:oauth",
        )
        created.append(app)
        docker(
            "run",
            "-d",
            "--rm",
            "--network",
            network,
            "--name",
            proxy,
            "-p",
            "127.0.0.1:19490:443",
            "-v",
            str(root / "nginx.conf") + ":/etc/nginx/nginx.conf:ro",
            "-v",
            str(root) + ":/cert:ro",
            "nginx:stable@sha256:9bf97bd7714f5e24c1ccd545ecb9eb5435cb6d109c97cebb15e7e455e0239edb",
        )
        created.append(proxy)
        with httpx.Client(verify=False, timeout=5, trust_env=False) as client:
            response = None

            for _ in range(40):
                try:
                    response = client.get("https://localhost:19490/app/info")
                    if response.status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.25)
            if response is None or response.status_code != 200:
                raise RuntimeError(
                    "Proxy did not become ready: " + docker("logs", app) + docker("logs", proxy)
                )

            assert response.json()["authMethods"] == ["token", "oauth"]
            assert response.json()["oauthMcpUrl"] == "https://mcpgame.paulox.dev/mcp"
            assert "set-cookie" not in response.headers
            response = client.get(
                "https://localhost:19490/.well-known/oauth-protected-resource/mcp",
                headers={"Host": "attacker.invalid", "X-Forwarded-Host": "internal:8000"},
            )
            assert response.status_code == 200
            assert response.json()["resource"] == "https://mcpgame.paulox.dev/mcp"
            response = client.get(
                "https://localhost:19490/.well-known/oauth-authorization-server",
                headers={"Host": "attacker.invalid"},
            )
            assert response.status_code == 200
            assert response.json()["issuer"] == "https://mcpgame.paulox.dev"
            assert response.json()["token_endpoint"] == "https://mcpgame.paulox.dev/oauth/token"
            response = client.get("https://localhost:19490/oauth/jwks")
            assert response.status_code == 200
            key = response.json()["keys"][0]
            assert key["kty"] == "RSA" and key["alg"] == "RS256"
            assert not set(key) & {"d", "p", "q", "dp", "dq", "qi"}
            assert response.headers["cache-control"] == "no-store"
            response = client.post("https://localhost:19490/mcp")
            assert response.status_code == 401
            assert "https://mcpgame.paulox.dev/.well-known/" in response.headers["www-authenticate"]
            response = client.get("https://localhost:19490/")
            assert response.status_code == 200
            asset = re.search(r'src="([^"]+\.js)"', response.text).group(1)
            assert client.get("https://localhost:19490" + asset).status_code == 200
        asyncio.run(client_check())
        asyncio.run(oauth_check())
        asyncio.run(oauth_check(host_first=True))
        hardening = json.loads(
            docker(
                "exec",
                app,
                "python",
                "-c",
                """
import json
import os
from pathlib import Path

status = Path('/proc/self/status').read_text().splitlines()
paths = ['/usr/bin/mount', '/usr/bin/umount', '/usr/bin/nsenter', '/usr/bin/infocmp', '/usr/bin/su']
print(json.dumps({
    'uid': os.getuid(),
    'capabilities': next(line.split()[1] for line in status if line.startswith('CapEff:')),
    'unusedExecutablesAbsent': all(not Path(p).exists() for p in paths),
}))
""",
            )
        )
        assert hardening == {
            "uid": 10001,
            "capabilities": "0000000000000000",
            "unusedExecutablesAbsent": True,
        }
        assert not docker("exec", app, "find", "/usr", "-xdev", "-type", "f", "-perm", "/6000")
        logs = docker("logs", app) + docker("logs", proxy)
        assert not re.search(
            r"(?:\?|&)(token|ticket|code|refresh_token|client_secret|state)=", logs
        )
        print(
            json.dumps(
                {
                    "https": True,
                    "embedded": True,
                    "publicSigningKey": True,
                    "discovery": True,
                    "challenge": True,
                    "canonicalSpoofResistance": True,
                    "staticAssets": True,
                    "websocket": True,
                    "officialMcpClient": True,
                    "oauthPkceToolsLogout": True,
                    "hostFirstAndBrowserFirst": True,
                    "browserReusesHostPlayer": True,
                    "publicEndpointBeforeLogin": True,
                    "nonRootNoCapabilities": True,
                    "noSetuidSetgid": True,
                    "unusedExecutablesAbsent": True,
                    "redactedLogs": True,
                    "nginxImage": json.loads(
                        docker(
                            "image",
                            "inspect",
                            "nginx:stable@sha256:9bf97bd7714f5e24c1ccd545ecb9eb5435cb6d109c97cebb15e7e455e0239edb",
                        )
                    )[0]["RepoDigests"],
                }
            )
        )
    finally:
        for name in reversed(created):
            subprocess.run(
                ["docker", "stop", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
        subprocess.run(
            ["docker", "network", "rm", network],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        subprocess.run(
            ["docker", "volume", "rm", volume], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
