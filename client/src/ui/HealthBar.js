import { healthRatio } from "../helpers/health.js";
import { Label } from "./Label.js";

const FRAME_W = 320;
const FRAME_H = 64;
const CAP = 24;
const SCALE = 0.82;
const GROOVE = { x: 14, y: 31, w: 292, h: 28 };

// the wooden health bar: a three-slice frame (two fixed caps and a stretched middle) with a gradient
// fill sized to the health ratio, the player name above it and the numeric health in the groove.
export class HealthBar {
    constructor(scene) {
        this.root = scene.add.container(0, 0).setScale(SCALE);
        const frame = scene.add
            .nineslice(0, 0, "hpbar", undefined, FRAME_W, FRAME_H, CAP, CAP, 0, 0)
            .setOrigin(0, 0);
        this.fill = scene.add.image(GROOVE.x, GROOVE.y, "hpfill").setOrigin(0, 0.5);
        this.name = new Label(scene, {
            x: 8,
            y: -8,
            size: "22px",
            color: "#fff2c2",
            stroke: "#20263a",
            strokeThickness: 5,
            originY: 1,
        });
        this.hp = new Label(scene, {
            x: FRAME_W / 2,
            y: GROOVE.y,
            size: "17px",
            stroke: "#3a1d12",
            originX: 0.5,
            originY: 0.5,
        });
        this.root.add([frame, this.fill, this.name.text, this.hp.text]);
    }

    update(entity) {
        this.root.setVisible(Boolean(entity));

        if (!entity) {
            return;
        }

        const ratio = healthRatio(entity.health, entity.maxHealth);
        this.fill.setVisible(ratio > 0).setDisplaySize(GROOVE.w * ratio, GROOVE.h);
        this.hp.setText(`${entity.health} / ${entity.maxHealth}`);
        this.name.setText(entity.name);
    }

    layout(x, y) {
        this.root.setPosition(x, y);
    }

    get height() {
        return FRAME_H * SCALE;
    }
}
