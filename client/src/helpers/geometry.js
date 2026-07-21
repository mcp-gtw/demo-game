// pure grid to pixel helpers and per-state visual mappings.

const FACING_ANGLE = {
    right: 0,
    down_right: Math.PI / 4,
    down: Math.PI / 2,
    down_left: (3 * Math.PI) / 4,
    left: Math.PI,
    up_left: (-3 * Math.PI) / 4,
    up: -Math.PI / 2,
    up_right: -Math.PI / 4,
};

export function cellCenter(cell, tile) {
    return { x: cell.x * tile + tile / 2, y: cell.y * tile + tile / 2 };
}

export function angleOf(facing) {
    return FACING_ANGLE[facing] ?? 0;
}

export function animForState(state) {
    if (state === "moving") {
        return "run";
    }

    if (state === "attacking" || state === "shooting") {
        return "attack";
    }

    return "idle";
}

export function facesLeft(facing) {
    return facing.includes("left");
}
