import Phaser from "phaser";
import { buildAnimations } from "../helpers/animations.js";
import { Clouds } from "../game/Clouds.js";
import { DamageNumbers } from "../game/DamageNumbers.js";
import { DebugOverlay } from "../game/DebugOverlay.js";
import { EntityView } from "../game/EntityView.js";
import { Music } from "../game/Music.js";
import {
    CLOUD_DENSITY_CELLS,
    CLOUD_MARGIN_CELLS,
    DPR,
    FOAM,
    FOAM_FRAME,
    OBJECT_TEXTURES,
    TREES,
    UNITS,
    WORLD_TEXTURES,
    unitBases,
} from "../constants.js";
import { interpolate } from "../helpers/interpolate.js";

const INTERP_DELAY_MS = 120;
const CAMERA_ZOOM = DPR;
const CLOUD_DEPTH = 20000;

// every pixel-art world texture stays nearest-filtered under the smooth (antialiased) renderer
const UNIT_TEXTURES = Object.entries(UNITS).flatMap(([key, unit]) =>
    unitBases(key, unit).flatMap((base) =>
        unit.attackRate ? [`${base}_idle`, `${base}_run`, `${base}_attack`] : [`${base}_idle`, `${base}_run`],
    ),
);
const CRISP = ["tileset", "foam", ...TREES.map((tree) => tree.key), ...Object.keys(WORLD_TEXTURES), ...UNIT_TEXTURES];

export class GameScene extends Phaser.Scene {
    constructor() {
        super("game");
    }

    init(data) {
        this.store = data.store;
        this.map = data.store.map;
        this.tile = this.map.tileSize;
        this.playerId = data.store.playerId;
        this.enemySprites = Object.fromEntries(
            Object.entries(data.store.catalog.enemies).map(([name, enemy]) => [name, enemy.sprite]),
        );
        this.views = new Map();
        this.knownIds = new Set();
        this.aliveState = new Map();
        this.pulseSeen = new Map();
        this.followed = null;
        this.primed = false;
    }

    preload() {
        this.load.setPath("/static");
        this.load.image("tileset", this.map.tileset.image);

        for (const item of Object.keys(this.store.catalog.items)) {
            this.load.image(`item_${item}`, `assets/items/${item}.png`);
        }
    }

    create() {
        const items = Object.keys(this.store.catalog.items).map((item) => `item_${item}`);

        for (const key of [...CRISP, ...Object.keys(OBJECT_TEXTURES), ...items]) {
            this.textures.get(key).setFilter(Phaser.Textures.FilterMode.NEAREST);
        }

        buildAnimations(this);
        this.#makeSparkTexture();
        this.damageNumbers = new DamageNumbers(this, this.tile);
        this.#buildWorld();

        const width = this.map.cols * this.tile;
        const height = this.map.rows * this.tile;
        const margin = this.tile * 6;
        this.cameras.main.setBounds(-margin, -margin, width + margin * 2, height + margin * 2);
        this.cameras.main.centerOn(width / 2, height / 2);
        this.cameras.main.setZoom(CAMERA_ZOOM);
        this.#buildClouds();
        this.music = new Music(this);
        this.debug = new DebugOverlay(this, this.map);

        // stop the track when the scene restarts on a fresh adoption, so music never stacks
        this.events.once("shutdown", () => this.music.stop());
    }

    update(_time, delta) {
        const entities = interpolate(this.store.buffer, this.tile, performance.now(), INTERP_DELAY_MS);
        this.#sync(entities, delta);
        this.clouds.update(delta);
        this.debug.update(entities.get(this.playerId)?.position);
    }

    #buildClouds() {
        const margin = CLOUD_MARGIN_CELLS * this.tile;
        const bounds = {
            minX: -margin,
            maxX: this.map.cols * this.tile + margin,
            minY: -margin,
            maxY: this.map.rows * this.tile + margin,
        };
        const layer = this.add.container(0, 0).setDepth(CLOUD_DEPTH);
        const count = Math.round((this.map.cols * this.map.rows) / CLOUD_DENSITY_CELLS);
        this.clouds = new Clouds(this, { layer, bounds, count });
    }

    #sync(entities, delta) {
        const present = new Set();

        for (const entity of entities.values()) {
            present.add(entity.id);
            const view = this.#viewFor(entity);
            view.update(entity, this.time.now, delta);

            if (this.primed && !this.knownIds.has(entity.id)) {
                this.#burst(entity.px, entity.py, 0xbfe9ff);
            }

            this.#lifecycle(entity);
            this.#vision(entity);
        }

        for (const [id, view] of this.views) {
            if (!present.has(id)) {
                // an enemy is dropped from the snapshot the instant it dies, so show its killing-blow
                // damage here since no health-zero frame ever arrives
                if (view.kind === "enemy" && view.lastHealth > 0) {
                    this.damageNumbers.spawn(view.container.x, view.container.y, view.lastHealth, "#ff5a4a");
                }

                this.#burst(view.container.x, view.container.y, 0xffe1b0);
                view.destroy();
                this.views.delete(id);
                this.aliveState.delete(id);
            }
        }

        this.#follow();
        this.knownIds = present;
        this.primed = true;
    }

    #viewFor(entity) {
        let view = this.views.get(entity.id);

        if (!view) {
            view = new EntityView(this, entity, this.tile, this.playerId);
            this.views.set(entity.id, view);
        }

        return view;
    }

    #buildWorld() {
        const width = this.map.cols * this.tile;
        const height = this.map.rows * this.tile;

        const ocean = this.add.tileSprite(-width, -height, width * 3, height * 3, "water");
        ocean.setOrigin(0, 0).setDepth(-10000);

        this.#buildFoam();
        this.#buildTilemap();
        this.#buildObjects();
    }

    #buildFoam() {
        // draw a synced foam rim on every sea cell touching land, nudged onto the coastline so the
        // grass tucks over its inner half and only the sea-side rim shows, hugging the shore
        for (let row = 0; row < this.map.rows; row += 1) {
            for (let col = 0; col < this.map.cols; col += 1) {
                if (this.map.ground[row * this.map.cols + col]) {
                    continue;
                }

                const toward = this.#landDirection(col, row);

                if (!toward) {
                    continue;
                }

                const x = col * this.tile + this.tile / 2 + toward.x * this.tile * FOAM.offset;
                const y = row * this.tile + this.tile / 2 + toward.y * this.tile * FOAM.offset;
                const foam = this.add.sprite(x, y, "foam");
                foam.setOrigin(0.5).setScale((this.tile * FOAM.scale) / FOAM_FRAME).setAlpha(FOAM.alpha).setDepth(-9500);
                foam.play("foam_drift");
            }
        }
    }

    #landDirection(col, row) {
        let dx = 0;
        let dy = 0;
        let found = false;

        for (const [nx, ny] of [[col + 1, row], [col - 1, row], [col, row + 1], [col, row - 1]]) {
            if (nx >= 0 && ny >= 0 && nx < this.map.cols && ny < this.map.rows && this.map.ground[ny * this.map.cols + nx]) {
                dx += nx - col;
                dy += ny - row;
                found = true;
            }
        }

        if (!found) {
            return null;
        }

        const len = Math.hypot(dx, dy) || 1;
        return { x: dx / len, y: dy / len };
    }

    #buildTilemap() {
        const first = this.map.tileset.firstGid;
        const grid = [];

        for (let row = 0; row < this.map.rows; row += 1) {
            const line = [];

            for (let col = 0; col < this.map.cols; col += 1) {
                const gid = this.map.ground[row * this.map.cols + col];
                line.push(gid ? gid - first : -1);
            }

            grid.push(line);
        }

        const tilemap = this.make.tilemap({ data: grid, tileWidth: this.tile, tileHeight: this.tile });
        const tiles = tilemap.addTilesetImage("tileset", "tileset", this.tile, this.tile, 0, 0);
        tilemap.createLayer(0, tiles, 0, 0).setDepth(-9000);
    }

    #buildObjects() {
        for (const obj of this.map.objects) {
            const sprite = this.add.image(0, 0, obj.sprite);
            const footprint = obj.w * this.tile;
            const baseY = (obj.y + obj.h) * this.tile;
            sprite.setOrigin(0.5, 1).setScale(footprint / sprite.width);
            sprite.setPosition(obj.x * this.tile + footprint / 2, baseY).setDepth(baseY);
        }
    }

    #vision(entity) {
        if (entity.kind !== "player" || entity.visionRange == null) {
            return;
        }

        const last = this.pulseSeen.get(entity.id);

        if (last === entity.visionPulseSeq) {
            return;
        }

        this.pulseSeen.set(entity.id, entity.visionPulseSeq);

        if (last === undefined) {
            return;
        }

        const ring = this.add.circle(entity.px, entity.py, this.tile * 0.4, 0x8fd6ff, 0.35);
        ring.setDepth(entity.py - 2);
        this.tweens.add({
            targets: ring,
            radius: entity.visionRange * this.tile,
            alpha: 0,
            duration: 900,
            ease: "Cubic.Out",
            onComplete: () => ring.destroy(),
        });
    }

    #lifecycle(entity) {
        if (entity.alive === undefined) {
            return;
        }

        const was = this.aliveState.get(entity.id);

        if (was === true && entity.alive === false) {
            this.#burst(entity.px, entity.py, 0xffe1b0);
        } else if (was === false && entity.alive === true) {
            this.#burst(entity.px, entity.py, 0xbfe9ff);
        }

        this.aliveState.set(entity.id, entity.alive);
    }

    #makeSparkTexture() {
        if (this.textures.exists("spark")) {
            return;
        }

        const g = this.make.graphics({ x: 0, y: 0, add: false });
        g.fillStyle(0xffffff, 1).fillCircle(8, 8, 8);
        g.generateTexture("spark", 16, 16);
        g.destroy();
    }

    #burst(x, y, color) {
        const emitter = this.add.particles(x, y - this.tile * 0.3, "spark", {
            speed: { min: 40, max: 150 },
            angle: { min: 0, max: 360 },
            scale: { start: 0.5, end: 0 },
            alpha: { start: 0.9, end: 0 },
            lifespan: 480,
            tint: color,
            emitting: false,
        });
        emitter.setDepth(y + 6000);
        emitter.explode(12);
        this.time.delayedCall(700, () => emitter.destroy());
    }

    #follow() {
        const view = this.views.get(this.playerId);

        if (view && this.followed !== view) {
            this.followed = view;
            this.cameras.main.startFollow(view.container, false, 0.12, 0.12);
        } else if (!view && this.followed) {
            this.followed = null;
            this.cameras.main.stopFollow();
        }
    }
}
