// the single mutable store the socket writes and the scenes read.

export function createStore() {
    return {
        catalog: null,
        map: null,
        buffer: [],
        playerId: null,
        phase: "menu",
        session: null,
        tools: [],
        status: "connecting",
        latencyMs: null,
        online: 0,
        me: null,
        requestStats: null,
    };
}

export function selfEntity(store) {
    const buffer = store.buffer;

    if (!buffer.length) {
        return null;
    }

    return buffer[buffer.length - 1].byId.get(store.playerId) ?? null;
}
