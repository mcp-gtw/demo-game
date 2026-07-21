import { INK, PANEL_BORDER, TEXT_DPR } from "../constants.js";

const PAD_X = 22;
const PAD_Y = 13;

// a parchment button whose background nine-slice is sized to fit its label, so it always grows
// with its content instead of clipping it
export class TextButton {
    constructor(scene, { text, onClick, size = "17px", color = INK, minWidth = 0 }) {
        this.scene = scene;
        this.onClick = onClick;

        this.label = scene.add
            .text(0, 0, text, { fontFamily: "Roboto, sans-serif", fontSize: size, fontStyle: "700", color })
            .setOrigin(0.5)
            .setResolution(TEXT_DPR);

        this.naturalWidth = Math.ceil(this.label.width) + PAD_X * 2;
        this.width = Math.max(minWidth, this.naturalWidth);
        this.height = Math.ceil(this.label.height) + PAD_Y * 2;

        const b = PANEL_BORDER;
        this.bg = scene.add
            .nineslice(0, 0, "panel9", undefined, this.width, this.height, b, b, b, b)
            .setOrigin(0.5)
            .setInteractive({ useHandCursor: true });

        this.bg.on("pointerover", () => this.bg.setTint(0xf6e6bf));
        this.bg.on("pointerout", () => this.bg.clearTint());
        this.bg.on("pointerdown", () => this.bg.setTint(0xd9c191));
        this.bg.on("pointerup", () => {
            this.bg.setTint(0xf6e6bf);
            this.onClick?.();
        });

        this.root = scene.add.container(0, 0, [this.bg, this.label]);
    }

    setWidth(width) {
        this.width = width;
        this.bg.setSize(width, this.height);
        return this;
    }

    setPosition(x, y) {
        this.root.setPosition(x, y);
        return this;
    }

    setText(value) {
        this.label.setText(value);
        return this;
    }
}
