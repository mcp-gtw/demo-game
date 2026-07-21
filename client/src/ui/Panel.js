import { PANEL_BORDER } from "../constants.js";

// a parchment window drawn as a Phaser nine-slice from the baked seamless panel texture.
export class Panel {
    constructor(scene, width, height) {
        const border = PANEL_BORDER;
        this.node = scene.add
            .nineslice(0, 0, "panel9", undefined, width, height, border, border, border, border)
            .setOrigin(0, 0);
    }

    setSize(width, height) {
        this.node.setSize(width, height);
        return this;
    }

    setPosition(x, y) {
        this.node.setPosition(x, y);
        return this;
    }
}
