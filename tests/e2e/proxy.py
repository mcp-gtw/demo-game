import asyncio
import json
import re
import secrets
import ssl
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

import httpx
import httpx2
import websockets
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
        APP_OIDC_ISSUER="https://auth.example",
        APP_OIDC_CLIENT_ID="browser",
        APP_OIDC_CLIENT_SECRET=secrets.token_urlsafe(32),
        APP_OAUTH_DATABASE_PATH="/data/oauth.sqlite",
        APP_ALLOWED_BROWSER_ORIGINS="https://mcpgame.paulox.dev",
        APP_OAUTH_MCP_CLIENT_IDS="host",
        GATEWAY_OAUTH_MODE="resource_server",
        GATEWAY_OAUTH_RESOURCE_URL="https://mcpgame.paulox.dev/mcp",
        GATEWAY_OAUTH_AUTHORIZATION_SERVERS="https://auth.example",
        GATEWAY_OAUTH_JWKS_URL="https://auth.example/jwks",
        GATEWAY_OAUTH_ALLOW_STATIC_MCP_TOKENS="true",
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
            "nginx:stable",
        )
        created.append(proxy)
        with httpx.Client(verify=False, timeout=5, trust_env=False) as client:
            for _ in range(40):
                try:
                    response = client.get("https://localhost:19490/app/info")
                    if response.status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.25)
            assert response.json()["authMethods"] == ["token", "oauth"]
            response = client.get(
                "https://localhost:19490/.well-known/oauth-protected-resource/mcp",
                headers={"Host": "attacker.invalid", "X-Forwarded-Host": "internal:8000"},
            )
            assert response.status_code == 200
            assert response.json()["resource"] == "https://mcpgame.paulox.dev/mcp"
            response = client.post("https://localhost:19490/mcp")
            assert response.status_code == 401
            assert "https://mcpgame.paulox.dev/.well-known/" in response.headers["www-authenticate"]
            response = client.get("https://localhost:19490/")
            assert response.status_code == 200
            asset = re.search(r'src="([^"]+\.js)"', response.text).group(1)
            assert client.get("https://localhost:19490" + asset).status_code == 200
        asyncio.run(client_check())
        logs = docker("logs", app) + docker("logs", proxy)
        assert not re.search(r"\?(token|ticket|code)=", logs)
        print(
            json.dumps(
                {
                    "https": True,
                    "discovery": True,
                    "challenge": True,
                    "canonicalSpoofResistance": True,
                    "staticAssets": True,
                    "websocket": True,
                    "officialMcpClient": True,
                    "redactedLogs": True,
                    "nginxImage": json.loads(docker("image", "inspect", "nginx:stable"))[0][
                        "RepoDigests"
                    ],
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
