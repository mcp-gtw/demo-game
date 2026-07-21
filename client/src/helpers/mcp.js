// builders for the connect snippets an agent pastes into its mcp client.

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
