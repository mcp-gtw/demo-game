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

afterEach(() => { vi.unstubAllGlobals(); localStorage.clear(); sessionStorage.clear(); });

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


it("restores each tab's method and a reopened browser's last method without tokens", async () => {
    const { controller, token, oauth, deps } = setup();
    await controller.restore();
    expect(token.connect).not.toHaveBeenCalled();
    localStorage.setItem("mcp-game-auth-method", "oauth");
    sessionStorage.setItem("mcp-game-auth-method", "token");
    await controller.restore();
    expect(token.connect).toHaveBeenCalledOnce();
    expect(deps.fetcher).not.toHaveBeenCalled();
    sessionStorage.clear();
    localStorage.setItem("mcp-game-auth-method", "oauth");
    await controller.restore();
    expect(deps.fetcher).toHaveBeenLastCalledWith("/app/oauth/session", { method: "POST" });
    expect(oauth.connect).toHaveBeenCalledOnce();
    expect([...Object.keys(localStorage)]).toEqual(["mcp-game-auth-method"]);
});

it("consumes the OAuth callback choice and ignores unsupported saved choices", async () => {
    const { controller, oauth, deps, store } = setup();
    await controller.restore(true);
    expect(deps.fetcher).toHaveBeenLastCalledWith("/app/oauth/consent", { method: "POST" });
    expect(oauth.connect).toHaveBeenCalledOnce();
    controller.expire();
    store.availableAuthMethods = ["token"];
    localStorage.setItem("mcp-game-auth-method", "invalid");
    await controller.restore(true);
    expect(oauth.connect).toHaveBeenCalledOnce();
});

it("expired restoration returns to the menu without redirect loops or Token downgrade", async () => {
    const { controller, store, token, oauth, deps } = setup({ fetcher: vi.fn(async () => ({ ok: false, status: 403 })) });
    localStorage.setItem("mcp-game-auth-method", "oauth");
    await controller.restore();
    expect(store.selectedAuthMethod).toBeNull();
    expect(localStorage.getItem("mcp-game-auth-method")).toBeNull();
    expect(sessionStorage.getItem("mcp-game-auth-method")).toBeNull();
    expect(deps.redirect).not.toHaveBeenCalled();
    expect(token.connect).not.toHaveBeenCalled();
    expect(oauth.connect).not.toHaveBeenCalled();
});

it.each([429, 503])("transient HTTP %s does not sign out or start another login", async status => {
    const { controller, store, deps } = setup({ fetcher: vi.fn(async () => ({ ok: false, status })) });
    localStorage.setItem("mcp-game-auth-method", "oauth");
    await expect(controller.restore()).rejects.toThrow("temporarily unavailable");
    expect(store.selectedAuthMethod).toBeNull();
    expect(localStorage.getItem("mcp-game-auth-method")).toBe("oauth");
    expect(deps.redirect).not.toHaveBeenCalled();
});

it("expired socket authorization cancels pending reconnects and clears the current identity", async () => {
    const { controller, token, store } = setup();
    await controller.select("token");
    controller.expire();
    expect(token.disconnect).toHaveBeenCalledOnce();
    expect(store.selectedAuthMethod).toBeNull();
});


it("network failures allow another selection without dropping a newer connection", async () => {
    let reject;
    const { controller, store, token } = setup({ fetcher: () => new Promise((resolve, fail) => { reject = fail; }) });
    const failed = controller.select("oauth");
    reject(new Error("offline"));
    await expect(failed).rejects.toThrow("offline");
    expect(store.selectedAuthMethod).toBeNull();
    const abandoned = controller.select("oauth");
    await controller.select("token");
    reject(new Error("offline"));
    await expect(abandoned).rejects.toThrow("offline");
    expect(store.selectedAuthMethod).toBe("token");
    expect(token.disconnect).not.toHaveBeenCalled();
});
