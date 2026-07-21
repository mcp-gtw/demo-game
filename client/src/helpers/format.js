// pure formatting helpers shared by the menu and the hud.

export function latencyLevel(latencyMs) {
    if (latencyMs == null) {
        return "unknown";
    }

    if (latencyMs < 80) {
        return "good";
    }

    if (latencyMs < 200) {
        return "fair";
    }

    return "poor";
}

const STATUS_LABEL = { connecting: "Connecting", online: "Live", offline: "Reconnecting" };

export function statusLabel(status) {
    return STATUS_LABEL[status] ?? status;
}

export function statusLine(status, latencyMs, online) {
    const latency = latencyMs == null ? "— ms" : `${latencyMs} ms`;
    return `${statusLabel(status)}    ${latency}    ${online} online`;
}

export function statRows(player) {
    const attributes = player.attributes;
    const resources = player.resources;

    return [
        ["Name", player.name],
        ["State", player.state],
        ["Health", `${player.health} / ${player.maxHealth}`],
        ["Position", `${player.position.x}, ${player.position.y}`],
        ["Facing", player.facing],
        ["Kills / Deaths", `${player.kills} / ${player.deaths}`],
        ["Wood / Gold", `${resources.wood} / ${resources.gold}`],
        ["Vision", `${attributes.visionRange} cells`],
        ["Move time", `${attributes.moveDuration}s`],
        ["Attack speed", `${attributes.attackSpeed}×`],
        ["Items", player.items.length ? player.items.join(", ") : "none"],
        ["Weapons", player.weapons.map((weapon) => weapon.name).join(", ")],
    ];
}
