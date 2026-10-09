"""Loopback-only test IdP, never included in an application distribution."""

import base64
import hashlib
import json
import os
import secrets
import time
from urllib.parse import parse_qs, urlencode

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI, Request
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse

app = FastAPI()
issuer = os.environ["TEST_ISSUER"]
resource = os.environ["TEST_RESOURCE"]
key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
codes = {}
transactions = {}


@app.get("/.well-known/openid-configuration")
@app.get("/.well-known/oauth-authorization-server")
async def discovery():
    return dict(
        issuer=issuer,
        authorization_endpoint=issuer + "/authorize",
        token_endpoint=issuer + "/token",
        jwks_uri=issuer + "/jwks",
        response_types_supported=["code"],
        grant_types_supported=["authorization_code"],
        code_challenge_methods_supported=["S256"],
        token_endpoint_auth_methods_supported=["client_secret_basic", "none"],
    )


@app.get("/jwks")
async def jwks():
    item = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    item.update(kid="local-test", use="sig", alg="RS256")
    return {"keys": [item]}


@app.get("/authorize")
async def authorize(request: Request):
    p = dict(request.query_params)
    expected = {
        "browser": resource.removesuffix("/mcp") + "/app/oauth/callback",
        "host": issuer + "/host-callback",
    }
    if (
        p.get("client_id") not in expected
        or p.get("redirect_uri") != expected[p["client_id"]]
        or p.get("code_challenge_method") != "S256"
        or p.get("response_type") != "code"
        or (p["client_id"] == "host" and p.get("resource") != resource)
    ):
        return JSONResponse({"error": "invalid_request"}, 400)
    transaction = secrets.token_urlsafe(32)
    transactions[transaction] = p | {"deadline": time.time() + 120}
    return HTMLResponse(
        "<h1>Local test identity provider</h1>"
        "<p>Test-only account: alice. Authorize access?</p>"
        '<form method="post" action="/approve">'
        '<input type="hidden" name="transaction" value="'
        + transaction
        + '"><button>Approve local test</button></form>'
    )


@app.post("/approve")
async def approve(request: Request):
    fields = parse_qs((await request.body()).decode())
    p = transactions.pop(fields.get("transaction", [""])[0], None)
    if p is None or p["deadline"] < time.time():
        return JSONResponse({"error": "invalid_request"}, 400)
    code = secrets.token_urlsafe(32)
    codes[code] = p
    return RedirectResponse(
        p["redirect_uri"] + "?" + urlencode(dict(code=code, state=p["state"], iss=issuer)), 303
    )


@app.get("/host-callback")
async def callback():
    return HTMLResponse("<h1>Local MCP authorization callback</h1>")


@app.post("/token")
async def token(request: Request):
    f = {k: v[0] for k, v in parse_qs((await request.body()).decode()).items()}
    p = codes.pop(f.get("code", ""), None)
    if p is None or p["deadline"] < time.time():
        return JSONResponse({"error": "invalid_grant"}, 400)
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(f.get("code_verifier", "").encode()).digest())
        .rstrip(b"=")
        .decode()
    )
    if (
        challenge != p["code_challenge"]
        or f.get("redirect_uri") != p["redirect_uri"]
        or f.get("client_id") != p["client_id"]
        or f.get("grant_type") != "authorization_code"
    ):
        return JSONResponse({"error": "invalid_grant"}, 400)
    now = int(time.time())
    common = dict(iss=issuer, sub="alice", iat=now, exp=now + 300)
    if p["client_id"] == "browser":
        basic = (
            "Basic " + base64.b64encode(("browser:" + os.environ["TEST_SECRET"]).encode()).decode()
        )
        if not secrets.compare_digest(request.headers.get("authorization", ""), basic):
            return JSONResponse({"error": "invalid_client"}, 401)
        value = jwt.encode(
            common | dict(aud="browser", nonce=p["nonce"]),
            key,
            algorithm="RS256",
            headers={"kid": "local-test"},
        )
        return dict(id_token=value, token_type="Bearer")
    if f.get("resource") != resource or p.get("scope") != "mcp:access":
        return JSONResponse({"error": "invalid_target"}, 400)
    value = jwt.encode(
        common | dict(aud=resource, client_id="host", scope="mcp:access"),
        key,
        algorithm="RS256",
        headers={"kid": "local-test", "typ": "at+jwt"},
    )
    return dict(access_token=value, token_type="Bearer", expires_in=300)
