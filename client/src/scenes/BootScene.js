import Phaser from "phaser";
import { LoadingWindow } from "../ui/LoadingWindow.js";
import {
    FOAM_FRAME,
    HUD_TEXTURES,
    MENU_TEXTURES,
    OBJECT_TEXTURES,
    TREES,
    UNITS,
    WORLD_TEXTURES,
    unitBases,
} from "../constants.js";

// loads every static asset once so no scene reloads a shared texture key. Only the tileset and item
// icons are dynamic (their paths arrive with the map and catalog) and stay in GameScene.
export class BootScene extends Phaser.Scene {
    constructor() {
        super("boot");
    }

    init(data) {
        this.store = data.store;
        this.gallery = data.gallery;
        this.onReady = data.onReady;
    }

    preload() {
        this.loading = new LoadingWindow(this);
        this.load.on("progress", (value) => this.loading.update(value));

        // every asset is part of the game, so any failed load is fatal and prompts a reload
        this.load.on("loaderror", () => {
            this.assetsFailed = true;
        });

        this.load.setPath("/static");

        const images = { ...MENU_TEXTURES, ...WORLD_TEXTURES, ...OBJECT_TEXTURES, ...HUD_TEXTURES };

        for (const [key, path] of Object.entries(images)) {
            this.load.image(key, path);
        }

        for (const [key, unit] of Object.entries(UNITS)) {
            const frame = { frameWidth: unit.frame, frameHeight: unit.frame };

            for (const base of unitBases(key, unit)) {
                const dir = unit.colored ? `${key}/${base.split("_")[0]}` : key;
                this.load.spritesheet(`${base}_idle`, `assets/units/${dir}/idle.png`, frame);
                this.load.spritesheet(`${base}_run`, `assets/units/${dir}/run.png`, frame);

                if (unit.attackRate) {
                    this.load.spritesheet(`${base}_attack`, `assets/units/${dir}/attack.png`, frame);
                }
            }
        }

        for (const tree of TREES) {
            this.load.spritesheet(tree.key, `assets/resources/${tree.key}.png`, {
                frameWidth: tree.frameWidth,
                frameHeight: tree.frameHeight,
            });
        }

        this.load.spritesheet("foam", "assets/terrain/foam.png", { frameWidth: FOAM_FRAME, frameHeight: FOAM_FRAME });
        this.load.audio("music", "assets/audio/music-bg.mp3");
    }

    create() {
        if (this.assetsFailed) {
            this.loading.showReload();
            return;
        }

        if (this.gallery) {
            this.scene.start("gallery", { store: this.store });
            return;
        }

        // login already resumed and ready during boot, so enterGame stopped this scene and we are done
        if (this.onReady()) {
            return;
        }

        // a resume is mid-flight (login arrived, catalog/map still coming): keep the loading screen up
        // until enterGame runs, so the landing never flashes before dropping into the game
        if (this.store.phase !== "game") {
            this.scene.start("login", { store: this.store });
        }
    }
}
