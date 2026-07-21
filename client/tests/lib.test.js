import { describe, expect, it } from "vitest";
import { claudeCommand, mcpEndpoint, mcpJson } from "../src/helpers/mcp.js";
import { latencyLevel, statRows, statusLabel, statusLine } from "../src/helpers/format.js";
import { indexWorld } from "../src/helpers/world.js";
import { createStore, selfEntity } from "../src/helpers/store.js";
import { angleOf, animForState, cellCenter, facesLeft } from "../src/helpers/geometry.js";
import { healthRatio } from "../src/helpers/health.js";
import { interpolate, pickFrames } from "../src/helpers/interpolate.js";

describe("mcp", () => {
    it("builds the claude command and json", () => {
        expect(claudeCommand("http://h/mcp/c", "tok")).toContain('mcp add --transport http mcp-game "http://h/mcp/c"');
        const parsed = JSON.parse(mcpJson("http://h/mcp/c", "tok"));
        expect(parsed.mcpServers["mcp-game"].headers.Authorization).toBe("Bearer tok");
    });

    it("rebuilds the endpoint on the browser origin, fixing a proxied scheme/host", () => {
        expect(mcpEndpoint("http://internal/mcp/abc", "https://game.example.dev")).toBe(
            "https://game.example.dev/mcp/abc",
        );
    });
});

describe("format", () => {
    it("grades latency", () => {
        expect(latencyLevel(null)).toBe("unknown");
        expect(latencyLevel(50)).toBe("good");
        expect(latencyLevel(120)).toBe("fair");
        expect(latencyLevel(400)).toBe("poor");
    });

    it("labels and lines the status", () => {
        expect(statusLabel("online")).toBe("Live");
        expect(statusLabel("weird")).toBe("weird");
        expect(statusLine("online", null, 3)).toBe("Live    — ms    3 online");
        expect(statusLine("online", 42, 3)).toBe("Live    42 ms    3 online");
    });

    it("builds stat rows with and without resources and items", () => {
        const base = {
            name: "a",
            state: "idle",
            health: 10,
            maxHealth: 20,
            position: { x: 1, y: 2 },
            facing: "up",
            kills: 0,
            deaths: 1,
            attributes: { visionRange: 6, moveDuration: 0.28, attackSpeed: 1 },
            resources: { wood: 0, gold: 0 },
            items: [],
            weapons: [{ name: "Sword" }],
        };
        const rows = statRows({ ...base, resources: { wood: 2, gold: 3 }, items: ["boots"] });
        expect(rows.find((r) => r[0] === "Wood / Gold")[1]).toBe("2 / 3");
        expect(rows.find((r) => r[0] === "Items")[1]).toBe("boots");
        const bare = statRows(base);
        expect(bare.find((r) => r[0] === "Wood / Gold")[1]).toBe("0 / 0");
        expect(bare.find((r) => r[0] === "Items")[1]).toBe("none");
    });
});

describe("world index", () => {
    it("flattens groups into a lookup", () => {
        const byId = indexWorld({
            players: [{ id: "p" }],
            enemies: [{ id: "e" }],
            projectiles: [],
            food: [{ id: "f" }],
            trees: [],
            pickups: [{ id: "k" }],
            coins: [{ id: "c" }],
        });
        expect([...byId.keys()].sort()).toEqual(["c", "e", "f", "k", "p"]);
    });
});

describe("store", () => {
    it("creates a store and resolves self", () => {
        const store = createStore();
        store.playerId = "me";
        expect(selfEntity(store)).toBeNull();
        store.buffer.push({ byId: new Map([["other", { id: "other" }]]) });
        expect(selfEntity(store)).toBeNull();
        store.buffer.push({ byId: new Map([["me", { id: "me" }]]) });
        expect(selfEntity(store).id).toBe("me");
    });
});

describe("geometry", () => {
    it("maps cells and facings", () => {
        expect(cellCenter({ x: 2, y: 3 }, 10)).toEqual({ x: 25, y: 35 });
        expect(angleOf("right")).toBe(0);
        expect(angleOf("nowhere")).toBe(0);
        expect(animForState("moving")).toBe("run");
        expect(animForState("attacking")).toBe("attack");
        expect(animForState("shooting")).toBe("attack");
        expect(animForState("idle")).toBe("idle");
        expect(facesLeft("up_left")).toBe(true);
        expect(facesLeft("right")).toBe(false);
    });
});

describe("health", () => {
    it("clamps the ratio", () => {
        expect(healthRatio(5, 0)).toBe(0);
        expect(healthRatio(-1, 10)).toBe(0);
        expect(healthRatio(20, 10)).toBe(1);
        expect(healthRatio(5, 10)).toBe(0.5);
    });
});

describe("interpolate", () => {
    const frame = (t, x) => ({ t, byId: new Map([["a", { id: "a", position: { x, y: 0 } }]]) });

    it("returns empty for an empty buffer", () => {
        expect(interpolate([], 10, 1000, 100).size).toBe(0);
    });

    it("handles a single-frame buffer", () => {
        const out = interpolate([frame(0, 3)], 10, 100, 0);
        expect(out.get("a").px).toBe(cellCenter({ x: 3, y: 0 }, 10).x);
    });

    it("picks the surrounding frames", () => {
        const buffer = [frame(0, 0), frame(100, 1), frame(200, 2)];
        expect(pickFrames(buffer, 150).older.t).toBe(100);
        expect(pickFrames(buffer, 999).older.t).toBe(0);
        expect(pickFrames(buffer, -10).older.t).toBe(0);
    });

    it("lerps between frames", () => {
        const buffer = [frame(0, 0), frame(100, 2)];
        const out = interpolate(buffer, 10, 150, 100);
        expect(out.get("a").px).toBeCloseTo(cellCenter({ x: 1, y: 0 }, 10).x);
    });

    it("snaps on a teleport and handles a missing previous frame", () => {
        const older = { t: 0, byId: new Map() };
        const newer = { t: 100, byId: new Map([["a", { id: "a", position: { x: 40, y: 0 } }]]) };
        const out = interpolate([older, newer], 10, 100, 0);
        expect(out.get("a").px).toBe(cellCenter({ x: 40, y: 0 }, 10).x);
    });

    it("snaps on a vertical teleport too", () => {
        const older = { t: 0, byId: new Map([["a", { id: "a", position: { x: 0, y: 0 } }]]) };
        const newer = { t: 100, byId: new Map([["a", { id: "a", position: { x: 0, y: 40 } }]]) };
        const out = interpolate([older, newer], 10, 100, 0);
        expect(out.get("a").py).toBe(cellCenter({ x: 0, y: 40 }, 10).y);
    });
});
