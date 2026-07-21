import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
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
