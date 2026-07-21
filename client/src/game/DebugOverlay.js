import { TEXT_DPR } from "../constants.js";

const DEPTH = 15000;
const COORD_STEP = 5;

// a togglable overlay (press B) that draws the Tiled cell grid, the blocked cells (sea plus solid
// object footprints), the spawn areas and the player's current cell, to verify the cell system.
export class DebugOverlay {
    constructor(scene, map) {
        this.scene = scene;
        this.map = map;
        this.tile = map.tileSize;
        this.visible = false;

        this.layer = scene.add.container(0, 0).setDepth(DEPTH).setVisible(false);
        this.grid = scene.add.graphics();
        this.marker = scene.add.graphics();
        this.layer.add([this.grid, this.marker]);
        this.#drawStatic();

        scene.input.keyboard.on("keydown-B", () => this.toggle());
    }

    toggle() {
        this.visible = !this.visible;
        this.layer.setVisible(this.visible);
    }

    update(cell) {
        if (!this.visible || !cell) {
            return;
        }

        this.marker.clear();
        this.marker.lineStyle(3, 0x62ff8a, 0.95).strokeRect(cell.x * this.tile, cell.y * this.tile, this.tile, this.tile);
    }

    #drawStatic() {
        const { cols, rows, ground, objects, spawns } = this.map;
        const w = cols * this.tile;
        const h = rows * this.tile;

        this.grid.fillStyle(0x1a66aa, 0.35);
        for (let row = 0; row < rows; row += 1) {
            for (let col = 0; col < cols; col += 1) {
                if (ground[row * cols + col] === 0) {
                    this.grid.fillRect(col * this.tile, row * this.tile, this.tile, this.tile);
                }
            }
        }

        this.grid.fillStyle(0xff5a4a, 0.3);
        for (const obj of objects.filter((o) => o.solid)) {
            // only the bottom rows (base) block, capped at 2, so a taller building's back stays open
            const solidRows = Math.min(obj.h, 2);
            const top = obj.y + obj.h - solidRows;
            this.grid.fillRect(obj.x * this.tile, top * this.tile, obj.w * this.tile, solidRows * this.tile);
        }

        this.grid.lineStyle(1, 0xffffff, 0.16);
        for (let col = 0; col <= cols; col += 1) {
            this.grid.lineBetween(col * this.tile, 0, col * this.tile, h);
        }
        for (let row = 0; row <= rows; row += 1) {
            this.grid.lineBetween(0, row * this.tile, w, row * this.tile);
        }

        for (const spawn of spawns) {
            const cx = (spawn.x + 0.5) * this.tile;
            const cy = (spawn.y + 0.5) * this.tile;
            this.grid.lineStyle(2, 0xffd23f, 0.8).strokeCircle(cx, cy, (spawn.range + 0.5) * this.tile);
            this.grid.fillStyle(0xffd23f, 0.9).fillCircle(cx, cy, this.tile * 0.18);
        }

        for (let row = 0; row < rows; row += COORD_STEP) {
            for (let col = 0; col < cols; col += COORD_STEP) {
                const label = this.scene.add
                    .text((col + 0.5) * this.tile, (row + 0.5) * this.tile, `${col},${row}`, {
                        fontFamily: "Roboto, sans-serif",
                        fontSize: "13px",
                        color: "#ffffff",
                    })
                    .setOrigin(0.5)
                    .setResolution(TEXT_DPR)
                    .setAlpha(0.6);
                this.layer.add(label);
            }
        }
    }
}
