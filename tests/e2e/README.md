# Local OAuth browser smoke

This test-only IdP is confined to loopback and is not part of the package. It has an explicit test account, ephemeral signing key and secret, exact registered callbacks, PKCE S256 and one-use codes. It is not a production login service or the gateway's embedded authorization server.

Run `make install`, then `npx --prefix client playwright install chromium` and `make oauth-smoke`. Alternatively set `TEST_CHROME` to an installed Chromium/Chrome executable. OpenSSL, Node 22.22.2+ and free local ports 19443/19470 are required. On macOS:

```sh
TEST_CHROME='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' make oauth-smoke
```

The runner creates a one-day self-signed test certificate and a temporary private SQLite database, starts an HTTPS game and HTTP loopback test IdP, and cleans up both processes/database. TLS verification is disabled only by the test clients for this self-signed localhost certificate. Production clients retain normal certificate verification.

Chrome drives the actual Phaser UI. The official Python MCP client initializes, lists ten tools, calls login/get_player/move for independent Token and OAuth characters. Authorization-code replay is rejected, and the game logout button revokes the OAuth channel. Screenshots in `/tmp/oauth-*.png` and `/tmp/token-game.png` show the method chooser, connection options and gameplay. They contain only ephemeral test accounts. The summary prints booleans and tool counts, never access tokens, codes, browser cookies or provider credentials.

This is local automation, not a ChatGPT/Claude cloud handshake or a public deployment test.

## Docker proxy smoke

Build the image with the locked dependencies and the coordinated gateway wheel with `make docker-build IMAGE=mcp-gtw-game:oauth`, then run `make proxy-smoke`. This creates and removes uniquely named local containers, a private Docker network and a data volume. It starts nginx with a temporary TLS certificate on port 19490, checks public canonical discovery URLs under forged Host headers, the direct anonymous 401 challenge, packaged assets, a Token WebSocket and the official MCP client through the proxy. The proxy uses the actual embedded authorization server and a temporary durable database/key. It verifies authorization server discovery and the public JWKS. The proxy also completes real embedded browser/host PKCE login, DCR, ticket issuance, gameplay and logout through HTTPS. The nginx image is pinned by digest. `make embedded-smoke` additionally drives the Phaser UI in Chrome. External IdP integration is covered by `make oauth-smoke`.

## Embedded production server

Run `make embedded-smoke` with TEST_CHROME when necessary. This starts the actual embedded authorization server inside the HTTPS game on port 19443 and uses an isolated private database/key and a real newly registered account. It does not start the simulator IdP. Chrome exercises browser sign-in, consent, DCR, host PKCE, the official MCP client and game tools, refresh, code replay rejection, logout and Token coexistence. Test-only TLS certificates remain confined to loopback.


To also run the MCP Inspector CLI against the authorized embedded server, set the verified Inspector version explicitly:

```sh
TEST_CHROME='/Applications/Google Chrome.app/Contents/MacOS/Google Chrome' TEST_INSPECTOR_VERSION=2.10.1 make embedded-smoke
```

The CLI trusts only the temporary test certificate through `NODE_EXTRA_CA_CERTS`, keeps its files in the temporary test directory, and must successfully list the ten game tools. The embedded smoke also requests `openid` and checks that the host receives its own ID token alongside the MCP access token.

Movement smokes wait for the public player state to become idle, try legal directions around blocked
cells, and assert an actual position change on the same player's ID. A successful HTTP response or
a tool error response does not count as gameplay success. The HTTPS proxy smoke also executes the
full embedded browser/host PKCE, DCR, ticket, tools and logout flow through nginx, and checks UID
10001, zero capabilities, no SUID/SGID binaries and removal of unused privileged executables.

Distribution checks inspect both wheel and sdist for the required app/web/dist/index.html and
assets, then compare repeated builds and run the installed game through HTTPS. `make build` builds
the frontend before packaging. A missing bundle is a build error.
