import Phaser from "phaser";
import "./style.css";
import { BootScene } from "./scenes/BootScene.js";
import { DPR } from "./constants.js";
import { GalleryScene } from "./scenes/GalleryScene.js";
import { AuthController } from "./helpers/auth.js";
import { OAuthGameSocket } from "./net/OAuthGameSocket.js";
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
let booted = false;

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
    const gallery = new URLSearchParams(location.search).has("gallery");
    game.scene.add("boot", BootScene, true, { store, gallery, onReady: onBoot });

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

// enter the game only once the assets have booted and login, catalog and map have all arrived, so a
// reload that resumes an already-logged-in session never races the boot into showing a stale landing
function enterGame() {
    if (started || !booted || store.phase !== "game" || !store.catalog || !store.map) {
        return false;
    }

    started = true;
    game.scene.start("game", { store });
    game.scene.start("hud", { store });
    game.scene.stop("login");
    game.scene.stop("boot");
    return true;
}

function onBoot() {
    booted = true;
    return enterGame();
}

function restartGame() {
    game.scene.start("game", { store });
    game.scene.start("hud", { store });
}

const wsScheme = location.protocol === "https:" ? "wss" : "ws";
const handlers = {
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
};

function resetAuth() {
    store.session = null;
    store.playerId = null;
    store.phase = "menu";
    store.catalog = null;
    store.map = null;
    store.buffer = [];
    store.me = null;
    started = false;

    if (game?.isBooted && booted) {
        game.scene.stop("game");
        game.scene.stop("hud");
        game.scene.start("login", { store });
    }
}

const baseUrl = `${wsScheme}://${location.host}/app/stream`;
const auth = new AuthController({ store, reset: resetAuth,
    createToken: () => new GameSocket(baseUrl, handlers),
    createOAuth: () => new OAuthGameSocket(baseUrl, handlers),
});
store.selectAuthMethod = (method) => auth.select(method).catch(() => { store.status = "offline"; });
store.switchAuth = () => auth.switchMethod().catch(() => { store.status = "offline"; });
store.requestStats = () => auth.requestStats();

async function pollInfo() {
    try {
        const info = await (await fetch("/app/info")).json();
        store.online = info.playersOnline;
        store.tools = info.tools ?? [];
        store.oauthMcpUrl = info.oauthMcpUrl;
        const changed = JSON.stringify(store.availableAuthMethods) !== JSON.stringify(info.authMethods);
        store.availableAuthMethods = info.authMethods;

        if (changed && booted && !store.selectedAuthMethod) {
            game.scene.start("login", { store });
        }
    } catch {
        // the landing shows the last known values until the next poll succeeds
    }
}

async function boot() {
    await loadFonts();
    await pollInfo();
    bootGame();
    const timer = setInterval(() => (store.phase === "game" ? clearInterval(timer) : pollInfo()), 3000);
    if (store.availableAuthMethods.length === 1 && store.availableAuthMethods[0] === "token") {
        store.selectAuthMethod("token");
    }
}

boot();
