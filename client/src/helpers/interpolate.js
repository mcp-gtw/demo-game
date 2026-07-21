import { cellCenter } from "./geometry.js";

// a jump beyond this many cells is a teleport (respawn) that snaps, not a slide to interpolate
const TELEPORT_CELLS = 2;

function lerp(a, b, t) {
    return a + (b - a) * t;
}

export function pickFrames(buffer, renderTime) {
    let older = buffer[0];
    let newer = buffer[buffer.length - 1];

    for (let i = 0; i < buffer.length - 1; i += 1) {
        if (buffer[i].t <= renderTime && buffer[i + 1].t >= renderTime) {
            older = buffer[i];
            newer = buffer[i + 1];
            break;
        }
    }

    return { older, newer };
}

export function interpolate(buffer, tile, now, delayMs) {
    const result = new Map();

    if (!buffer.length) {
        return result;
    }

    const renderTime = now - delayMs;
    const { older, newer } = pickFrames(buffer, renderTime);
    const span = newer.t - older.t;
    const alpha = span > 0 ? Math.min(1, Math.max(0, (renderTime - older.t) / span)) : 1;

    for (const [id, entity] of newer.byId) {
        const prev = older.byId.get(id) || entity;
        const teleport =
            Math.abs(prev.position.x - entity.position.x) > TELEPORT_CELLS ||
            Math.abs(prev.position.y - entity.position.y) > TELEPORT_CELLS;
        const from = cellCenter(prev.position, tile);
        const to = cellCenter(entity.position, tile);
        const px = teleport ? to.x : lerp(from.x, to.x, alpha);
        const py = teleport ? to.y : lerp(from.y, to.y, alpha);
        result.set(id, { ...entity, px, py });
    }

    return result;
}
