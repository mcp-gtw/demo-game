import { beforeEach, expect, it, vi } from "vitest";

const fakes = vi.hoisted(() => {
    class Node {
        constructor() { this.width = 100; this.height = 20; this.value = ""; }
        add() { return this; }
        setScale() { return this; }
        setDepth() { return this; }
        setOrigin() { return this; }
        setPosition() { return this; }
        setY() { return this; }
        setWordWrapWidth(width) { if (width <= 0) { throw new Error("Invalid wrap width"); } return this; }
        setResolution() { return this; }
        setVisible(visible) { this.visible = visible; return this; }
        setText(value) { this.value = value; return this; }
    }
    class Scene {}
    class TextButton {
        constructor(scene, options) { this.options = options; this.root = new Node(); this.height = 40; this.naturalWidth = 220; }
        setWidth() { return this; }
        setPosition() { return this; }
    }
    class Panel { constructor() { this.node = new Node(); } setSize() {} }
    const windows = [];
    class Window { constructor(scene, options) { this.options = options; this.closed = false; windows.push(this); } close() { this.closed = true; } }
    class Clouds { constructor(scene, options) { this.bounds = options.bounds; } update() {} }
    return { Node, Scene, TextButton, Panel, Window, Clouds, windows };
});

vi.mock("phaser", () => ({ default: { Scene: fakes.Scene, Textures: { FilterMode: { NEAREST: 0 } } } }));
vi.mock("../src/game/Clouds.js", () => ({ Clouds: fakes.Clouds }));
vi.mock("../src/ui/TextButton.js", () => ({ TextButton: fakes.TextButton }));
vi.mock("../src/ui/Panel.js", () => ({ Panel: fakes.Panel }));
vi.mock("../src/ui/Window.js", () => ({ Window: fakes.Window }));
import { LoginScene } from "../src/scenes/LoginScene.js";

function sceneFor({ method = "token", available = ["token", "oauth"], session = null } = {}) {
    const store = { availableAuthMethods: available, selectedAuthMethod: method, session,
        online: 2, status: "connecting", tools: [], selectAuthMethod: vi.fn(), switchAuth: vi.fn() };
    const scene = new LoginScene();
    scene.add = { container: () => new fakes.Node(), image: () => new fakes.Node(), text: (x, y, value) => new fakes.Node().setText(value) };
    scene.textures = { get: () => ({ setFilter() {} }) };
    scene.scale = { gameSize: { width: 1200, height: 800 }, on: vi.fn(), off: vi.fn() };
    scene.events = { once: vi.fn() };
    scene.init({ store });
    scene.create();
    return { scene, store };
}

beforeEach(() => { fakes.windows.length = 0; });

it("dual offers both methods before creating any browser session", () => {
    const { scene, store } = sceneFor({ method: null });
    expect(scene.authButtons.map((button) => button.options.text)).toEqual(["Connect with Token", "Connect with OAuth"]);
    expect(scene.loginButton.root.visible).toBe(false);
    scene.authButtons[0].options.onClick();
    scene.authButtons[1].options.onClick();
    expect(store.selectAuthMethod.mock.calls).toEqual([["token"], ["oauth"]]);
    scene.update(0, 16);
    expect(scene.status.value).toContain("Choose Token");
});

it("Token preserves all four options, separate copies and switching", () => {
    const { scene, store } = sceneFor();
    scene.loginButton.options.onClick();
    expect(scene.revealed).toBe(false);
    scene.update(0, 16);
    store.status = "offline";
    scene.update(0, 16);
    expect(scene.status.value).toBe("Reconnecting…");
    store.session = { mcpUrl: "https://game/mcp/channel", mcpToken: "mcp-secret" };
    scene.update(0, 16);
    scene.update(0, 16);
    scene.loginButton.options.onClick();
    expect(scene.optionButtons.slice(0, 4).map((button) => button.options.text)).toEqual(["Claude Code (CLI)", "MCP Config (mcp.json)", "Endpoint + Token", "Tools"]);
    for (const button of scene.optionButtons) { button.options.onClick(); }
    expect(fakes.windows[0].options.body).toContain("mcp-secret");
    expect(fakes.windows[1].options.body).toContain("Authorization");
    expect(fakes.windows[2].options.copies.map((copy) => copy.value)).toEqual([store.session.mcpUrl, "mcp-secret"]);
    expect(fakes.windows[3].options.body).toContain("tool list loads");
    expect(store.switchAuth).toHaveBeenCalledOnce();
    store.tools = [{ name: "move", description: "Move the player" }];
    scene.optionButtons[3].options.onClick();
    expect(fakes.windows.at(-1).options.body).toContain("Move the player");
    scene.loginButton.options.onClick();
    scene.scale.gameSize = { width: 200, height: 200 };
    scene.scale.on.mock.calls[0][1].call(scene);
    scene.events.once.mock.calls[0][1]();
    expect(scene.scale.off).toHaveBeenCalled();
});

it("OAuth shows URL/config only and signs out without any token copy", () => {
    const { scene, store } = sceneFor({ method: "oauth", available: ["oauth"], session: { authMethod: "oauth", mcpUrl: "https://game/mcp/channel" } });
    scene.update(0, 16);
    scene.loginButton.options.onClick();
    for (const button of scene.optionButtons) { button.options.onClick(); }
    expect(fakes.windows).toHaveLength(4);
    expect(fakes.windows[0].options.copies).toEqual([{ label: "Copy URL", value: store.session.mcpUrl }]);
    expect(fakes.windows.map((window) => window.options.body).join(" ")).not.toContain("Authorization:");
    expect(fakes.windows.map((window) => window.options.body).join(" ")).not.toContain("mcpToken");
    expect(store.switchAuth).toHaveBeenCalledOnce();
});

it("legacy keeps the Token menu without a method selector", () => {
    const { scene } = sceneFor({ available: ["token"], session: { mcpUrl: "url", mcpToken: "token" } });
    scene.update(0, 16);
    scene.loginButton.options.onClick();
    expect(scene.authButtons).toHaveLength(0);
    expect(scene.optionButtons).toHaveLength(4);
});
