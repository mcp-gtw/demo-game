import { afterEach, expect, it, vi } from "vitest";
import { AuthController } from "../src/helpers/auth.js";
import { oauthClaudeCommand, oauthMcpJson } from "../src/helpers/mcp.js";

function setup(options = {}) {
    const store = { availableAuthMethods: ["token", "oauth"], selectedAuthMethod: null };
    const token = { connect: vi.fn(), disconnect: vi.fn(), requestStats: vi.fn() };
    const oauth = { connect: vi.fn(), disconnect: vi.fn(), requestStats: vi.fn() };
    const deps = { store, createToken: () => token, createOAuth: () => oauth,
        reset: vi.fn(), fetcher: vi.fn(async () => ({ ok: true })), redirect: vi.fn(), ...options };
    return { store, token, oauth, deps, controller: new AuthController(deps) };
}

afterEach(() => vi.unstubAllGlobals());

it("Token and OAuth are independent choices in the same controller", async () => {
    const { controller, store, token, oauth, deps } = setup();
    controller.requestStats();
    await controller.select("token");
    expect(store.selectedAuthMethod).toBe("token");
    expect(deps.fetcher).not.toHaveBeenCalled();
    controller.requestStats();
    expect(token.requestStats).toHaveBeenCalledOnce();
    await controller.select("oauth");
    expect(token.disconnect).toHaveBeenCalledOnce();
    expect(oauth.connect).toHaveBeenCalledOnce();
    await controller.switchMethod();
    expect(oauth.disconnect).toHaveBeenCalledOnce();
    expect(store.selectedAuthMethod).toBeNull();
    expect(deps.fetcher).toHaveBeenLastCalledWith("/app/oauth/logout", { method: "POST" });
    await controller.select("token");
    await controller.switchMethod();
    expect(deps.fetcher).toHaveBeenCalledTimes(2);
});

it("requires an enabled auth method", async () => {
    const { controller } = setup();
    await expect(controller.select("unknown")).rejects.toThrow("unavailable");
    await controller.switchMethod();
});

it("OAuth authentication redirects to login and never downgrades to Token", async () => {
    const { controller, token, oauth, deps } = setup({ fetcher: async () => ({ ok: false }) });
    await controller.select("oauth");
    expect(deps.redirect).toHaveBeenCalledWith("/app/oauth/login");
    expect(token.connect).not.toHaveBeenCalled();
    expect(oauth.connect).not.toHaveBeenCalled();
});

it("a pending consent cannot reconnect an abandoned OAuth method", async () => {
    let resolve;
    const { controller, token, oauth } = setup({ fetcher: () => new Promise((res) => { resolve = res; }) });
    const pending = controller.select("oauth");
    await controller.select("token");
    resolve({ ok: true });
    await pending;
    expect(oauth.connect).not.toHaveBeenCalled();
    expect(token.connect).toHaveBeenCalledOnce();
});

it("uses same-origin fetch and the configured login navigation by default", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => ({ ok: false })));
    const assign = vi.fn();
    vi.stubGlobal("location", { assign });
    const controller = new AuthController({ store: { availableAuthMethods: ["oauth"] },
        createToken: vi.fn(), createOAuth: vi.fn(), reset: vi.fn() });
    await controller.select("oauth");
    expect(assign).toHaveBeenCalledWith("/app/oauth/login");
});

it("OAuth connection snippets contain a URL and no Bearer header", () => {
    const url = "https://game.example/mcp/channel";
    expect(oauthClaudeCommand(url)).toBe(`claude mcp add --transport http mcp-game ${url}`);
    expect(JSON.parse(oauthMcpJson(url))).toEqual({ mcpServers: { "mcp-game": { type: "http", url } } });
    expect(oauthMcpJson(url)).not.toContain("Authorization");
});
