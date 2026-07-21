import { TEXT_DPR } from "../constants.js";

// floating combat numbers: each hit spawns the amount taken, rising and fading in a slightly random
// direction so overlapping hits fan out instead of stacking.
export class DamageNumbers {
    constructor(scene, tile) {
        this.scene = scene;
        this.tile = tile;
    }

    spawn(x, y, amount, color) {
        const startY = y - this.tile * 0.6;
        const text = this.scene.add
            .text(x, startY, String(amount), {
                fontFamily: "Roboto, sans-serif",
                fontSize: "20px",
                fontStyle: "800",
                color,
                stroke: "#20263a",
                strokeThickness: 5,
            })
            .setOrigin(0.5)
            .setResolution(TEXT_DPR)
            .setDepth(y + 9000);

        const drift = (Math.random() - 0.5) * this.tile * 1.6;
        const rise = this.tile * (1.4 + Math.random() * 0.8);

        this.scene.tweens.add({
            targets: text,
            x: x + drift,
            y: startY - rise,
            alpha: { from: 1, to: 0 },
            scale: { from: 1.15, to: 0.8 },
            duration: 720 + Math.random() * 260,
            ease: "Quad.Out",
            onComplete: () => text.destroy(),
        });
    }
}
