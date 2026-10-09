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

Build the image with the locked PyPI dependencies with `make docker-build IMAGE=mcp-gtw-game:oauth`, then run `make proxy-smoke`. This creates and removes uniquely named local containers, a private Docker network and a data volume. It starts nginx with a temporary TLS certificate on port 19490, checks public canonical discovery URLs under forged Host headers, the direct anonymous 401 challenge, packaged assets, a Token WebSocket and the official MCP client through the proxy. The IdP URL is a placeholder; no OAuth token or browser identity is fetched in this proxy-specific test. HTTP-to-IdP/browser OAuth is covered by `make oauth-smoke`.
