import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { OAuthGameSocket } from "../src/net/OAuthGameSocket.js";
import { GameSocket } from "../src/net/GameSocket.js";

class FakeWebSocket {
    static OPEN = 1;
    static instances = [];

    constructor(url) {
        this.url = url;
        this.readyState = FakeWebSocket.OPEN;
        this.listeners = {};
        this.sent = [];
        FakeWebSocket.instances.push(this);
    }

    addEventListener(type, cb) {
        (this.listeners[type] ??= []).push(cb);
    }

    emit(type, event) {
        (this.listeners[type] ?? []).forEach((cb) => cb(event));
    }

    send(data) {
        this.sent.push(data);
    }

    close() {
        this.readyState = 3;
        this.emit("close");
    }
}

function handlers() {
    return {
        onStatus: vi.fn(),
        onSession: vi.fn(),
        onLogin: vi.fn(),
        onCatalog: vi.fn(),
        onMap: vi.fn(),
        onSnapshot: vi.fn(),
        onMe: vi.fn(),
    };
}

const UUID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa";

beforeEach(() => {
    FakeWebSocket.instances = [];
    global.WebSocket = FakeWebSocket;
    const store = new Map();
    vi.stubGlobal("localStorage", {
        getItem: (key) => (store.has(key) ? store.get(key) : null),
        setItem: (key, value) => store.set(key, String(value)),
        removeItem: (key) => store.delete(key),
        clear: () => store.clear(),
    });
    vi.stubGlobal("crypto", { randomUUID: () => UUID });
    vi.useFakeTimers();
});

afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
});

function lastSocket() {
    return FakeWebSocket.instances[FakeWebSocket.instances.length - 1];
}

describe("GameSocket", () => {
    it("mints a token, connects with it and dispatches every message", () => {
        const h = handlers();
        const socket = new GameSocket("ws://host/app/stream", h);
        socket.connect();

        expect(localStorage.getItem("mcp-game-token")).toBe(UUID);
        expect(lastSocket().url).toBe(`ws://host/app/stream?token=${UUID}`);
        expect(h.onStatus).toHaveBeenCalledWith("connecting", null);

        lastSocket().emit("open");
        expect(h.onStatus).toHaveBeenCalledWith("online", null);

        const send = (msg) => lastSocket().emit("message", { data: JSON.stringify(msg) });
        send({ type: "session", mcpUrl: "u", mcpToken: "t" });
        expect(h.onSession).toHaveBeenCalled();
        send({ type: "login", player: { id: "p" } });
        expect(h.onLogin).toHaveBeenCalledWith({ id: "p" });
        send({ type: "catalog", catalog: { a: 1 } });
        expect(h.onCatalog).toHaveBeenCalled();
        send({ type: "map", map: { cols: 1 } });
        expect(h.onMap).toHaveBeenCalled();
        send({ type: "snapshot", world: { players: [] } });
        expect(h.onSnapshot).toHaveBeenCalled();
        send({ type: "me", player: { id: "p" } });
        expect(h.onMe).toHaveBeenCalled();
        send({ type: "pong", id: 1 });
        expect(h.onStatus).toHaveBeenCalledWith("online", expect.any(Number));
        send({ type: "unknown" });

        lastSocket().emit("close");
        expect(h.onStatus).toHaveBeenLastCalledWith("offline", null);
    });

    it("reuses the token already stored in localStorage", () => {
        localStorage.setItem("mcp-game-token", "kept-token");
        const socket = new GameSocket("ws://host/app/stream", handlers());
        socket.connect();
        expect(lastSocket().url).toBe("ws://host/app/stream?token=kept-token");
    });

    it("pings while open, answers stats and stops pinging when not open", () => {
        const socket = new GameSocket("ws://host/app/stream", handlers());
        socket.connect();
        const ws = lastSocket();
        ws.emit("open");
        const pings = () => ws.sent.filter((m) => m.includes('"ping"')).length;
        vi.advanceTimersByTime(2000);
        expect(pings()).toBe(1);
        socket.requestStats();
        expect(ws.sent.some((m) => m.includes('"me"'))).toBe(true);

        ws.readyState = 0;
        vi.advanceTimersByTime(2000);
        expect(pings()).toBe(1);
    });

    it("does not send once the socket is closed", () => {
        const socket = new GameSocket("ws://host/app/stream", handlers());
        socket.connect();
        const ws = lastSocket();
        ws.emit("open");
        ws.close();
        socket.requestStats();
        expect(ws.sent.some((m) => m.includes('"me"'))).toBe(false);
    });

    it("reconnects with backoff and clears the stale timer on the next close", () => {
        const socket = new GameSocket("ws://host/app/stream", handlers());
        socket.connect();
        const first = lastSocket();
        first.emit("open");
        first.close();
        vi.advanceTimersByTime(10000);
        const second = lastSocket();
        expect(second).not.toBe(first);
        second.close();
        vi.advanceTimersByTime(10000);
        expect(FakeWebSocket.instances.length).toBeGreaterThan(2);
    });

    it("handles each connection's teardown once even when error and close both fire", () => {
        const socket = new GameSocket("ws://host/app/stream", handlers());
        socket.connect();
        const ws = lastSocket();
        ws.emit("error");
        expect(ws.readyState).toBe(3);
        ws.emit("close"); // ignored: this connection was already torn down
        vi.advanceTimersByTime(10000);
    });

    it("tolerates missing handlers", () => {
        const socket = new GameSocket("ws://host/app/stream", {});
        socket.connect();
        const ws = lastSocket();
        ws.emit("open");
        ws.emit("message", { data: JSON.stringify({ type: "session", mcpUrl: "u", mcpToken: "t" }) });
        ws.emit("message", { data: JSON.stringify({ type: "login", player: {} }) });
        ws.emit("message", { data: JSON.stringify({ type: "catalog", catalog: {} }) });
        ws.emit("message", { data: JSON.stringify({ type: "map", map: {} }) });
        ws.emit("message", { data: JSON.stringify({ type: "snapshot", world: {} }) });
        ws.emit("message", { data: JSON.stringify({ type: "me", player: {} }) });
        ws.emit("message", { data: JSON.stringify({ type: "pong" }) });
        socket.requestStats();
        ws.close();
        vi.advanceTimersByTime(10000);
    });
});

const settle = async () => { for (let i = 0; i < 12; i++) { await Promise.resolve(); } };

it("disconnect cancels a reconnect and preserves the Token UUID", () => {
    const socket = new GameSocket("ws://host/app/stream", handlers());
    socket.disconnect();
    socket.connect();
    const ws = lastSocket();
    ws.emit("open");
    socket.disconnect();
    vi.advanceTimersByTime(10000);
    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(ws.readyState).toBe(3);
    expect(localStorage.getItem("mcp-game-token")).toBe(UUID);
});

it("OAuth uses a fresh one-use ticket on every reconnect without localStorage", async () => {
    let number = 0;
    const ticket = vi.fn(async () => ({ ok: true, json: async () => ({ ticket: `ticket-${++number}` }) }));
    const socket = new OAuthGameSocket("wss://host/app/stream", handlers(), ticket);
    socket.connect();
    await settle();
    expect(lastSocket().url).toBe("wss://host/app/stream?ticket=ticket-1");
    expect(localStorage.getItem("mcp-game-token")).toBeNull();
    lastSocket().emit("close");
    await vi.advanceTimersByTimeAsync(1000);
    await settle();
    expect(lastSocket().url).toBe("wss://host/app/stream?ticket=ticket-2");
    socket.disconnect();
});

it("ticket failures retry OAuth and never open a Token socket", async () => {
    const ticket = vi.fn(async () => ({ ok: false }));
    const socket = new OAuthGameSocket("wss://host/app/stream", handlers(), ticket);
    socket.connect();
    await settle();
    expect(ticket).toHaveBeenCalledOnce();
    expect(FakeWebSocket.instances).toHaveLength(0);
    socket.disconnect();
    await vi.advanceTimersByTimeAsync(10000);
    expect(ticket).toHaveBeenCalledOnce();
});

it("late ticket resolutions and rejections cannot reopen a disconnected socket", async () => {
    let resolve;
    let reject;
    const pending = new Promise((res, rej) => { resolve = res; reject = rej; });
    const socket = new GameSocket("wss://host/app/stream", {}, () => pending);
    socket.connect();
    socket.disconnect();
    resolve("wss://host/app/stream?ticket=old");
    await settle();
    expect(FakeWebSocket.instances).toHaveLength(0);
    const rejected = new Promise((res, rej) => { reject = rej; });
    const second = new GameSocket("wss://host/app/stream", {}, () => rejected);
    second.connect();
    second.disconnect();
    reject(new Error("offline"));
    await settle();
    expect(FakeWebSocket.instances).toHaveLength(0);
});

it("only the latest connection attempt may open a websocket", async () => {
    let resolve;
    const first = new Promise((res) => { resolve = res; });
    const urls = vi.fn().mockReturnValueOnce(first).mockResolvedValueOnce("wss://host/new");
    const socket = new GameSocket("wss://host/app/stream", {}, urls);
    socket.connect();
    await settle();
    socket.connect();
    await settle();
    resolve("wss://host/old");
    await settle();
    expect(FakeWebSocket.instances).toHaveLength(1);
    expect(lastSocket().url).toBe("wss://host/new");
    socket.disconnect();
});

it("OAuth default fetch requests a ticket without exposing Bearer credentials", async () => {
    const fetcher = vi.fn(async () => ({ ok: true, json: async () => ({ ticket: "one" }) }));
    vi.stubGlobal("fetch", fetcher);
    const socket = new OAuthGameSocket("wss://host/app/stream", {});
    socket.connect();
    await settle();
    expect(fetcher).toHaveBeenCalledWith("/app/oauth/ticket", { method: "POST" });
    socket.disconnect();
});

it("stale open and message events cannot restore an abandoned method", () => {
    const h = handlers();
    const socket = new GameSocket("ws://host/app/stream", h);
    socket.connect();
    const ws = lastSocket();
    socket.disconnect();
    ws.emit("open");
    ws.emit("message", { data: JSON.stringify({ type: "session", mcpToken: "old" }) });
    expect(h.onSession).not.toHaveBeenCalled();
    expect(h.onStatus).not.toHaveBeenCalledWith("online", null);
});


it.each([401, 403])("OAuth HTTP %s requests reauthentication and stops reconnecting", async status => {
    let socket;
    const onAuthRequired = vi.fn(() => socket.disconnect());
    socket = new OAuthGameSocket("wss://host/app/stream", { onAuthRequired }, async () => ({ ok: false, status }));
    socket.connect();
    await settle();
    expect(onAuthRequired).toHaveBeenCalledOnce();
    expect(socket.reconnectTimer).toBeNull();
    expect(FakeWebSocket.instances).toHaveLength(0);
});

it("unauthorized OAuth never requires a callback to keep credentials private", async () => {
    const socket = new OAuthGameSocket("wss://host/app/stream", {}, async () => ({ ok: false, status: 403 }));
    socket.connect();
    await settle();
    expect(FakeWebSocket.instances).toHaveLength(0);
    socket.disconnect();
});


it("a denied obsolete ticket cannot sign out a newer connection", async () => {
    let resolve;
    const fetcher = vi.fn().mockReturnValueOnce(new Promise(done => { resolve = done; }))
        .mockResolvedValueOnce({ ok: true, json: async () => ({ ticket: "current" }) });
    const onAuthRequired = vi.fn();
    const socket = new OAuthGameSocket("wss://host/app/stream", { onAuthRequired }, fetcher);
    socket.connect();
    await settle();
    socket.connect();
    await settle();
    resolve({ ok: false, status: 403 });
    await settle();
    expect(onAuthRequired).not.toHaveBeenCalled();
    expect(lastSocket().url).toBe("wss://host/app/stream?ticket=current");
    expect(socket.stopped).toBe(false);
    socket.disconnect();
});

it("a denied abandoned OAuth ticket cannot clear the selected Token identity", async () => {
    let resolve;
    const onAuthRequired = vi.fn();
    const socket = new OAuthGameSocket("wss://host/app/stream", { onAuthRequired }, () => new Promise(done => { resolve = done; }));
    socket.connect();
    await settle();
    socket.disconnect();
    resolve({ ok: false, status: 401 });
    await settle();
    expect(onAuthRequired).not.toHaveBeenCalled();
    expect(socket.reconnectTimer).toBeNull();
});
