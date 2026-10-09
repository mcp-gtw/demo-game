# Game authentication

`APP_MCP_AUTH_MODE=legacy` is the default: the browser keeps its UUID in localStorage, opens `/app/stream?token=<UUID>`, receives the original MCP URL and `mcp-UUID` token, and keeps all four connection options. OAuth is not required in this mode.

`dual` displays **Connect with Token** and **Connect with OAuth** before opening a game session. Both methods work in the same process. Token uses the unchanged UUID flow and original clipboard builders. OAuth never reads that UUID, receives no MCP bearer token, and uses a separate account-owned random channel. The game still runs tools through the Python `LocalProvider`; it does not use the JavaScript provider SDK.

`oauth` offers only OAuth. `dual` requires `GATEWAY_OAUTH_ALLOW_STATIC_MCP_TOKENS=true`; `oauth` requires false. Inconsistent modes fail at startup. Legacy channels alone are eligible for the hybrid static-token path.

## External identity provider

An IdP is the service that signs users in and issues verified identities and access tokens. Register a confidential **browser BFF client** and separate public **MCP host clients** with Authorization Code and PKCE S256. Browser identity and MCP access-token identity must use the same issuer and subject namespace. Cross-issuer account linking is not implemented.

The browser callback is exactly `https://mcpgame.paulox.dev/app/oauth/callback`. The MCP resource/audience is exactly `https://mcpgame.paulox.dev/mcp`, even though the game provides a channel-specific `/mcp/<id>` endpoint. The external IdP must validate exact registered MCP host callback URLs and `resource` in both authorization and token requests, and issue access JWTs with `typ=at+jwt`, `iss`, `sub`, `aud`, `exp`, `client_id` and `scope=mcp:access`. Choose an IdP/client registration method supported by your intended host; the game does not supply CIMD or DCR.

Copy `.env.oauth.example`, replace the issuer, JWKS endpoint, client IDs and secret using your IdP's real configuration, and set a writable private persistent database path. Never put the browser client secret in frontend configuration or source control. The example domain names are placeholders, not a usable login service.

## Browser flow and revocation

The BFF creates a short-lived login transaction with state, nonce and PKCE. Callback verifies the issuer response, transaction cookie, one-use state, signature, ID-token audience and nonce. Duplicate/ambiguous session and login-state cookies are rejected on HTTP and WebSocket entry. The session cookie is Secure, HttpOnly, SameSite=Lax and restricted to `/app`. SQLite stores hashes of cookie/ticket identifiers, private transaction payloads and finite expiries. New databases are created with mode 0600; keep existing databases and their directory private. Protect this database as sensitive data: PKCE verifiers exist temporarily in login payloads. Browser OAuth tokens are not sent to localStorage, clipboard, logs or the WebSocket.

Choosing OAuth is explicit consent for the configured `APP_OAUTH_MCP_CLIENT_IDS` to control this account's game channel. The BFF grants access only to those exact issuer/subject/client tuples, bounded by the browser session expiry. Expired durable grants are purged transactionally, including orphaned generations after restart. Configure this allowlist narrowly. The frontend then obtains a cookie-bound, origin-bound, single-use WebSocket ticket (30 seconds by default). Every reconnect needs a new ticket. Mixing token and ticket parameters is rejected. The provider credential is internal and is never a substitute for OAuth.

OAuth connect options contain the MCP endpoint, a Claude command without an Authorization header, MCP JSON without a bearer token, and Tools. The MCP host completes its own OAuth login/consent at the IdP. Static Token keeps its original command, JSON, endpoint/token and Tools buttons.

**Switch / Sign out** closes the previous socket, invalidates pending reconnections, clears player/map/session caches, and signs out/revokes an OAuth channel. Logout and changing accounts revoke grants and close live OAuth streams without affecting Token users. Multiple tabs for the same account intentionally share one active OAuth channel. Browser session expiry is fixed; activity does not renew the cookie automatically. Game frames recheck the session and stop after expiry or revocation. A reconnect during the configured grace interval retains the account channel; after teardown or restart a new random generation is created and must be consented again.

SQLite is a single-host persistence adapter. Owned HTTP clients close on shutdown. Game state, channel ownership and MCP session bindings remain process-local; multiple replicas require a coordinated routing/state design. Login and authenticated BFF actions use bounded per-address rate budgets. Proxy client-address trust must be explicitly configured. OAuth/dual HTML allows only self-hosted scripts, limits WebSocket connections to the configured origin, blocks framing/objects, and suppresses Referer headers. Inline style is allowed for the Phaser canvas/UI. The supplied nginx file redacts query logs and proxies static assets from the packaged application.

## Local verification and remaining work

`make oauth-smoke` builds the frontend and runs a loopback-only test IdP, HTTPS game, Chrome and the official Python MCP client. It exercises simultaneous Token/OAuth login, tool calls, one-use authorization code and logout revocation, and writes screenshots to `/tmp`. Its IdP is test-only and must never be deployed. See `tests/e2e/README.md` for requirements.

Unit/ASGI tests cover hostile tokens, callback/state/origin checks, one-use ticket races, account changes, grace reconnects, credential separation, dual modes and actual LoginScene rendering with Phaser fakes. The implementation report records executed checks separately from pending ones. The gateway embedded AS is unavailable. Real ChatGPT and Claude OAuth tests, a production IdP and public deployment remain pending. Do not infer remote host interoperability solely from local tests.
