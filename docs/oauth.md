# Game authentication

`APP_MCP_AUTH_MODE=legacy` is the default: the browser keeps its UUID in localStorage, opens `/app/stream?token=<UUID>`, receives the original MCP URL and `mcp-UUID` token, and keeps all four connection options. OAuth is not required in this mode.

`dual` displays **Connect with Token** and **Connect with OAuth** before opening a game session. Both methods work in the same process. Token uses the unchanged UUID flow and original clipboard builders. OAuth never reads that UUID, receives no MCP bearer token, and uses a separate account-owned random channel. The game still runs tools through the Python `LocalProvider`; it does not use the JavaScript provider SDK.

`oauth` offers only OAuth. `dual` requires `GATEWAY_OAUTH_ALLOW_STATIC_MCP_TOKENS=true`; `oauth` requires false. Inconsistent modes fail at startup. Legacy channels alone are eligible for the hybrid static-token path.

## External identity provider

An IdP is the service that signs users in and issues verified identities and access tokens. Register a confidential **browser BFF client** and separate public **MCP host clients** with Authorization Code and PKCE S256. Browser identity and MCP access-token identity must use the same issuer and subject namespace. Cross-issuer account linking is not implemented.

The browser callback is exactly `https://mcpgame.paulox.dev/app/oauth/callback`. The MCP resource/audience is exactly `https://mcpgame.paulox.dev/mcp`, even though the game provides a channel-specific `/mcp/<id>` endpoint. The external IdP must validate exact registered MCP host callback URLs and `resource` in both authorization and token requests, and issue access JWTs with `typ=at+jwt`, `iss`, `sub`, `aud`, `exp`, `client_id` and `scope=mcp:access`. Choose an IdP/client registration method supported by your intended host; the external IdP supplies client registration.

Copy `.env.oauth.external.example`, replace the issuer, JWKS endpoint, client IDs and secret using your IdP's real configuration, and set a writable private persistent database path. Never put the browser client secret in frontend configuration or source control. The example domain names are placeholders, not a usable login service.

## Browser flow and revocation

The browser login transaction and state cookie use APP_OAUTH_LOGIN_TIMEOUT_SECONDS (600 seconds,
maximum 1800). This allows account creation and consent without the former two-minute callback
deadline. The deadline is absolute and expired state remains invalid even if its cookie is replayed.
Keep this timeout aligned with the authorization server's login/consent window. The gateway 0.0.7
embedded server still has a two-minute login window. Its separate-window fix must be published to
PyPI before upgrading this project's dependency, and the browser timeout change alone does not
extend that older server window.

The BFF creates a short-lived login transaction with state, nonce and PKCE. Callback verifies the issuer response, transaction cookie, one-use state, signature, ID-token audience and nonce. Duplicate/ambiguous session and login-state cookies are rejected on HTTP and WebSocket entry. The session cookie is Secure, HttpOnly, SameSite=Lax and restricted to `/app`. SQLite stores hashes of cookie/ticket identifiers, private transaction payloads and finite expiries. New databases are created with mode 0600; keep existing databases and their directory private. Protect this database as sensitive data: PKCE verifiers exist temporarily in login payloads. Browser OAuth tokens are not sent to localStorage, clipboard, logs or the WebSocket.

Choosing OAuth is explicit consent for the configured `APP_OAUTH_MCP_CLIENT_IDS` to control this account's game channel. The BFF grants access only to those exact issuer/subject/client tuples, bounded by the browser session expiry. Expired durable grants are purged transactionally, including orphaned generations after restart. Configure this allowlist narrowly. The frontend then obtains a cookie-bound, origin-bound, single-use WebSocket ticket (30 seconds by default). Every reconnect needs a new ticket. Mixing token and ticket parameters is rejected. The provider credential is internal and is never a substitute for OAuth.

OAuth connect options contain the MCP endpoint, a Claude command without an Authorization header, MCP JSON without a bearer token, and Tools. The MCP host completes its own OAuth login/consent at the IdP. Static Token keeps its original command, JSON, endpoint/token and Tools buttons.

**Switch / Sign out** closes the previous socket, invalidates pending reconnections, clears player/map/session caches, and signs out/revokes an OAuth channel. Logout and changing accounts revoke grants and close live OAuth streams without affecting Token users. Multiple tabs for the same account intentionally share one active OAuth channel. Browser session expiry is fixed; activity does not renew the cookie automatically. Game frames recheck the session and stop after expiry or revocation. A reconnect during the configured grace interval retains the account channel; after teardown or restart a new random generation is created and must be consented again.

SQLite is a single-host persistence adapter. Owned HTTP clients close on shutdown. Game state, channel ownership and MCP session bindings remain process-local; multiple replicas require a coordinated routing/state design. Login and authenticated BFF actions use bounded IP and verified-account budgets. APP_OAUTH_BROWSER_RATE_LIMIT_REQUESTS (30), APP_OAUTH_BROWSER_RATE_LIMIT_WINDOW_SECONDS (60) and APP_OAUTH_BROWSER_RATE_LIMIT_MAXIMUM_KEYS (10000) configure each budget. They use the gateway progressive backoff settings and return HTTP 429 with Retry-After. Replace AppGateway.browser_oauth_class or inject BrowserOAuth(rate_limit=..., principal_limit=...) to use another limiter. Proxy client-address trust must be explicitly configured. OAuth/dual HTML allows only self-hosted scripts, limits WebSocket connections to the configured origin, blocks framing/objects, and suppresses Referer headers. Inline style is allowed for the Phaser canvas/UI. The supplied nginx file redacts query logs and proxies static assets from the packaged application.

## Local verification and remaining work

`make oauth-smoke` builds the frontend and runs a loopback-only test IdP, HTTPS game, Chrome and the official Python MCP client. It exercises simultaneous Token/OAuth login, tool calls, one-use authorization code and logout revocation, and writes screenshots to `/tmp`. Its IdP is test-only and must never be deployed. See `tests/e2e/README.md` for requirements.

Unit/ASGI tests cover hostile tokens, callback/state/origin checks, one-use ticket races, account changes, grace reconnects, credential separation, dual modes and actual LoginScene rendering with Phaser fakes. Real ChatGPT and Claude account/workspace tests and public deployment remain pending; local tests exercise the actual embedded server as well as the external-IdP path.

## Embedded login on the game domain

With gateway 0.0.7, `.env.oauth.example` enables Token + OAuth at `https://mcpgame.paulox.dev` without an external IdP. The issuer is that exact origin. The gateway serves `/.well-known/oauth-authorization-server`, `/.well-known/openid-configuration`, `/oauth/authorize`, `/oauth/login`, `/oauth/consent`, `/oauth/token`, `/oauth/jwks` and `/oauth/revoke`. Optional `/oauth/register` supports bounded public-client DCR; the example explicitly enables it. CIMD is enabled by default for public HTTPS client metadata with DNS/peer validation and bounded fetching; private_key_jwt is not advertised.

Set a private persistent `/data` volume owned by UID/GID 10001. `oauth.sqlite` contains real accounts, browser sessions, hashed codes/refresh identifiers and grants; `oauth.sqlite.key` contains the persistent RSA private key (0600). Back up both together. The key is generated only when missing and never put in the environment, frontend or image. Replacing it invalidates signed tokens. The browser client ID/secret are pre-registered from APP_OIDC_CLIENT_ID/APP_OIDC_CLIENT_SECRET; generate a random secret once and retain it across restarts. The browser callback is `/app/oauth/callback`.

`APP_OAUTH_ACCOUNT_REGISTRATION_ENABLED` defaults false. The embedded example explicitly enables self-service accounts; the real sign-in page offers account creation and username/password login. Passwords are salted PBKDF2-HMAC-SHA256 with 600,000 iterations, processed in bounded background workers. There are no default accounts or passwords. Disable registration after creating accounts if this is a private deployment. Signing in is separate from the MCP `login` tool, which creates the playable character.

After browser login, select OAuth in the game to authorize its channel. Each MCP host registers its exact callback and then receives a separate named consent screen. Approval grants only the authenticated account's current channel; no guessed channel or email-based account linking. `APP_OAUTH_MCP_CLIENT_IDS` can be empty in embedded mode, because dynamically registered clients receive explicit approval in that screen; an external IdP still requires the fixed allowlist. Hosts can use safe CIMD, opt-in DCR or pre-registration. They must include the canonical `/mcp` resource in both authorization and token requests and use PKCE S256. OAuth tool listings declare their scopes in securitySchemes and _meta; tool denials include the reauthentication challenge without invoking LocalProvider.

Codes are short-lived and consumed atomically. Refresh tokens rotate atomically; replay revokes the entire family, including existing access JWTs. Access verification checks the family in SQLite rather than relying only on JWT expiry. Game logout/channel removal revokes families, login sessions and pending codes for that subject. Channel generations are bound at consent and checked again at exchange/refresh, so an old grant cannot authorize a replacement session. Previously admitted tool executions may finish; new requests/emissions are denied.

Run `make embedded-smoke` (with TEST_CHROME if needed) to exercise the actual production AS in Chrome over local HTTPS: account registration, browser PKCE, DCR host consent, official MCP initialize/tools/login/move, refresh, code replay rejection, logout and simultaneous Token. No simulator IdP is used for this target.

Build the image with `make docker-build IMAGE=mcp-gtw-game:oauth` or `docker build -t mcp-gtw-game:oauth .`. The lockfile installs gateway 0.0.7 from PyPI with verified artifact hashes. Development, CI and Docker builds do not require a sibling checkout or GATEWAY_INTEGRATION_SHA. Version 0.0.6 cannot run embedded OAuth. The supplied proxy must forward `/oauth/`, `/app/` and `/.well-known/` as well as `/mcp`; keep OAuth request queries out of logs.


The final local container scan retains upstream Debian package alerts from the requested Python 3.14 slim base; it does not claim a zero-CVE image. The gateway's [container applicability review](https://github.com/mcp-gtw/mcp-gtw/blob/main/docs/security.md#container-audit-scope) records the affected CLI/privileged components and the tested non-root runtime. Python and npm dependencies had no known audit vulnerabilities in that run.

Channel grants retain the approved scopes per client. A broader token cannot expand a read-only
client's grant. Explicit re-consent replaces the scope set, and revoking one client preserves another
client's grant until channel logout/removal revokes all of them. Tests exercise this distinction.

The gateway coordinated acceptance workflow takes complete gateway/game/provider commit SHAs and
executes the three-project gates, Chrome/Inspector flows and Docker HTTPS smoke. Game tests and
images use the published gateway selected by the game lockfile. The final grant schema stores
approved scopes and requires
new grant storage for the feature, without historical-schema compatibility code.

Explicit host consent writes a grant through GameConsentPolicy.approve. Authorization-code exchange
and refresh use GameConsentPolicy.validate, which only reads current grants. They cannot recreate a
revoked grant or restore previously removed scopes. Saturated password workers reject new work
with HTTP 429, preventing a waiting queue from growing without a bound.

The base .env.example also lists all optional OAuth settings with their defaults. Embedded and
external examples provide complete mode-specific values. Run `make build` for distributions. Hatch
explicitly includes the built frontend in wheel and sdist despite the development gitignore.
Packaging fails if the required bundle is missing, preventing a successful Python-only game artifact.

Session cookie names must be ASCII identifiers. Invalid or Unicode cookie names fail settings
validation at startup, before a login handler attempts to emit an invalid HTTP cookie.
