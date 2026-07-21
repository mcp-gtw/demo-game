// the browser's single session socket: connect info, login, world snapshots, stats and latency.

const RECONNECT_MIN_MS = 500;
const RECONNECT_MAX_MS = 8000;
const PING_INTERVAL_MS = 2000;
const TOKEN_KEY = "mcp-game-token";

function ownToken() {
    let token = localStorage.getItem(TOKEN_KEY);

    if (!token) {
        token = crypto.randomUUID();
        localStorage.setItem(TOKEN_KEY, token);
    }

    return token;
}

export class GameSocket {
    constructor(baseUrl, handlers) {
        this.baseUrl = baseUrl;
        this.handlers = handlers;
        this.socket = null;
        this.token = ownToken();
        this.latencyMs = null;
        this.reconnectAttempt = 0;
        this.reconnectTimer = null;
        this.pingTimer = null;
    }

    connect() {
        this.handlers.onStatus?.("connecting", this.latencyMs);
        const url = `${this.baseUrl}?token=${encodeURIComponent(this.token)}`;
        const socket = new WebSocket(url);
        this.socket = socket;

        socket.addEventListener("open", () => {
            this.reconnectAttempt = 0;
            this.handlers.onStatus?.("online", this.latencyMs);
            this.#startPing();
        });
        socket.addEventListener("message", (event) => this.#onMessage(event.data));
        socket.addEventListener("close", () => this.#onClose(socket));
        socket.addEventListener("error", () => socket.close());
    }

    requestStats() {
        this.#send({ type: "me" });
    }

    #onMessage(raw) {
        const message = JSON.parse(raw);

        switch (message.type) {
            case "session":
                this.handlers.onSession?.(message);
                break;
            case "login":
                this.handlers.onLogin?.(message.player);
                break;
            case "catalog":
                this.handlers.onCatalog?.(message.catalog);
                break;
            case "map":
                this.handlers.onMap?.(message.map);
                break;
            case "snapshot":
                this.handlers.onSnapshot?.(message.world);
                break;
            case "me":
                this.handlers.onMe?.(message.player);
                break;
            case "pong":
                this.latencyMs = Math.round(performance.now() - message.id);
                this.handlers.onStatus?.("online", this.latencyMs);
                break;
        }
    }

    #onClose(socket) {
        // a socket can report both error and close, so handle each connection's teardown once
        if (this.socket !== socket) {
            return;
        }

        this.socket = null;
        this.latencyMs = null;
        this.#stopPing();
        this.handlers.onStatus?.("offline", this.latencyMs);
        const backoff = Math.min(RECONNECT_MIN_MS * 2 ** this.reconnectAttempt, RECONNECT_MAX_MS);
        const delay = Math.round(backoff * (0.8 + Math.random() * 0.4));
        this.reconnectAttempt += 1;

        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
        }

        this.reconnectTimer = setTimeout(() => this.connect(), delay);
    }

    #startPing() {
        this.#stopPing();
        this.pingTimer = setInterval(() => {
            if (this.socket?.readyState === WebSocket.OPEN) {
                this.#send({ type: "ping", id: performance.now() });
            }
        }, PING_INTERVAL_MS);
    }

    #stopPing() {
        if (this.pingTimer) {
            clearInterval(this.pingTimer);
            this.pingTimer = null;
        }
    }

    #send(message) {
        if (this.socket?.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify(message));
        }
    }
}
