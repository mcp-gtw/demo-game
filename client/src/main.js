import Phaser from "phaser";
import "./style.css";
import { BootScene } from "./scenes/BootScene.js";
import { DPR } from "./constants.js";
import { GalleryScene } from "./scenes/GalleryScene.js";
import { GameSocket } from "./net/GameSocket.js";
import { GameScene } from "./scenes/GameScene.js";
import { HudScene } from "./scenes/HudScene.js";
import { LoginScene } from "./scenes/LoginScene.js";
import { createStore } from "./helpers/store.js";
import { mcpEndpoint } from "./helpers/mcp.js";
import { indexWorld } from "./helpers/world.js";

const BUFFER_LIMIT = 20;

const store = createStore();
let game = null;
let started = false;

async function loadFonts() {
    if (!document.fonts) {
        return;
    }

    try {
        await Promise.all([document.fonts.load('400 16px "Roboto"'), document.fonts.load('700 16px "Roboto"')]);
    } catch {
        // the canvas falls back to a system font if Roboto cannot load
    }
}

function bootGame() {
    game = new Phaser.Game({
        type: Phaser.AUTO,
        parent: "game",
        backgroundColor: "#2b6a86",
        render: { antialias: true, roundPixels: true },
        scale: { mode: Phaser.Scale.NONE, width: window.innerWidth * DPR, height: window.innerHeight * DPR },
    });
    game.scene.add("game", GameScene, false);
    game.scene.add("hud", HudScene, false);
    game.scene.add("login", LoginScene, false);
    game.scene.add("gallery", GalleryScene, false);
    game.scene.add("boot", BootScene, true, { store, gallery: new URLSearchParams(location.search).has("gallery") });

    const applyCss = () => {
        game.canvas.style.width = `${window.innerWidth}px`;
        game.canvas.style.height = `${window.innerHeight}px`;
        game.scale.refresh();
    };
    game.events.once("ready", applyCss);
    window.addEventListener("resize", () => {
        if (!game.isBooted) {
            return;
        }

        game.scale.resize(window.innerWidth * DPR, window.innerHeight * DPR);
        applyCss();
    });
}

function enterGame() {
    if (started || store.phase !== "game" || !store.catalog || !store.map) {
        return;
    }

    started = true;
    game.scene.start("game", { store });
    game.scene.start("hud", { store });
    game.scene.stop("login");
}

function restartGame() {
    game.scene.start("game", { store });
    game.scene.start("hud", { store });
}

const wsScheme = location.protocol === "https:" ? "wss" : "ws";
const socket = new GameSocket(`${wsScheme}://${location.host}/app/stream`, {
    onSession: (info) => {
        store.session = { ...info, mcpUrl: mcpEndpoint(info.mcpUrl, location.origin) };
    },
    onLogin: (player) => {
        const readopted = store.phase === "game" && store.playerId !== player.id;
        store.playerId = player.id;
        store.phase = "game";

        if (readopted) {
            restartGame();
        } else {
            enterGame();
        }
    },
    onCatalog: (catalog) => {
        store.catalog = catalog;
        enterGame();
    },
    onMap: (map) => {
        store.map = map;
        enterGame();
    },
    onSnapshot: (world) => {
        store.buffer.push({ t: performance.now(), byId: indexWorld(world) });
        store.online = world.players.length;

        if (store.buffer.length > BUFFER_LIMIT) {
            store.buffer.shift();
        }
    },
    onMe: (player) => {
        store.me = player;
    },
    onStatus: (status, latencyMs) => {
        store.status = status;
        store.latencyMs = latencyMs;

        if (status !== "online") {
            store.online = 0;
        }
    },
});

store.requestStats = () => socket.requestStats();

async function pollInfo() {
    try {
        const info = await (await fetch("/app/info")).json();
        store.online = info.playersOnline;
        store.tools = info.tools ?? [];
    } catch {
        // the landing shows the last known values until the next poll succeeds
    }
}

async function boot() {
    await loadFonts();
    bootGame();
    pollInfo();
    const timer = setInterval(() => (store.phase === "game" ? clearInterval(timer) : pollInfo()), 3000);
    socket.connect();
}

boot();
