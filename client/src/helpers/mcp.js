// builders for the connect snippets an agent pastes into its mcp client.

// rebuild the mcp endpoint on the browser's own origin, keeping only the channel path from the server.
// A TLS-terminating proxy (nginx, Cloudflare) reaches the server as plain http, so the server-built
// scheme/host can be wrong; the browser's origin is always the real one.
export function mcpEndpoint(mcpUrl, origin) {
    return `${origin}${new URL(mcpUrl, origin).pathname}`;
}

export function claudeCommand(url, token) {
    return (
        `claude mcp remove mcp-game 2>/dev/null || true; ` +
        `claude mcp add --transport http mcp-game "${url}" ` +
        `--header "Authorization: Bearer ${token}"`
    );
}

export function mcpJson(url, token) {
    return JSON.stringify(
        {
            mcpServers: {
                "mcp-game": { type: "http", url, headers: { Authorization: `Bearer ${token}` } },
            },
        },
        null,
        2,
    );
}
