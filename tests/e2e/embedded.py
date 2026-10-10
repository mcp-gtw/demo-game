import contextlib
import os
import pathlib
import secrets
import socket
import subprocess
import tempfile
import time

root = pathlib.Path(__file__).resolve().parents[2]
fixture = pathlib.Path(__file__).parent
for port in (19443, 19470):
    with socket.socket() as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", port))
with tempfile.TemporaryDirectory(prefix="oauth-local-") as temp:
    p = pathlib.Path(temp)
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
            str(p / "key.pem"),
            "-out",
            str(p / "cert.pem"),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    env = os.environ | dict(
        TEST_SECRET=secrets.token_urlsafe(32),
        TEST_ISSUER="https://localhost:19443",
        TEST_RESOURCE="https://localhost:19443/mcp",
        TEST_CERTIFICATE=str(p / "cert.pem"),
        TEST_STORAGE_DIR=str(p / "inspector"),
    )
    env.update(
        APP_MCP_AUTH_MODE="dual",
        APP_PUBLIC_BASE_URL="https://localhost:19443",
        APP_OIDC_ISSUER=env["TEST_ISSUER"],
        APP_OIDC_CLIENT_ID="browser",
        APP_OIDC_CLIENT_SECRET=env["TEST_SECRET"],
        APP_OAUTH_DATABASE_PATH=str(p / "oauth.db"),
        APP_ALLOWED_BROWSER_ORIGINS="https://localhost:19443",
        APP_OAUTH_MCP_CLIENT_IDS="host",
        APP_OAUTH_ALLOW_LOCALHOST_HTTP="true",
        GATEWAY_OAUTH_MODE="embedded",
        GATEWAY_OAUTH_EMBEDDED_DCR_ENABLED="true",
        APP_OAUTH_ACCOUNT_REGISTRATION_ENABLED="true",
        GATEWAY_OAUTH_RESOURCE_URL=env["TEST_RESOURCE"],
        GATEWAY_OAUTH_AUTHORIZATION_SERVERS=env["TEST_ISSUER"],
        GATEWAY_OAUTH_JWKS_URL=env["TEST_ISSUER"] + "/oauth/jwks",
        GATEWAY_OAUTH_ALLOW_LOCALHOST_HTTP="true",
        GATEWAY_OAUTH_ALLOW_STATIC_MCP_TOKENS="true",
        GATEWAY_ALLOWED_MCP_ORIGINS="",
        PYTHONPATH=str(root / "src"),
    )
    children = []
    logs = contextlib.ExitStack()
    try:
        for args, name in [
            (
                [
                    "app.main:app",
                    "--port",
                    "19443",
                    "--ssl-keyfile",
                    str(p / "key.pem"),
                    "--ssl-certfile",
                    str(p / "cert.pem"),
                ],
                "game",
            ),
        ]:
            log = logs.enter_context((p / (name + ".log")).open("w"))
            children.append(
                subprocess.Popen(
                    [
                        str(root / ".venv/bin/python"),
                        "-m",
                        "uvicorn",
                        *args,
                        "--host",
                        "127.0.0.1",
                        "--no-access-log",
                    ],
                    cwd=root,
                    env=env,
                    stdout=log,
                    stderr=log,
                )
            )
        time.sleep(3)
        assert all(c.poll() is None for c in children)
        subprocess.run(
            ["node", str(root / "client/tests/embedded-browser-smoke.mjs")],
            cwd=root,
            env=env
            | dict(
                TEST_HOST_SCRIPT=str(fixture / "host.py"),
                TEST_PYTHON=str(root / ".venv/bin/python"),
            ),
            check=True,
        )
    finally:
        for c in children:
            c.terminate()
        for c in children:
            c.wait(timeout=15)
        logs.close()
