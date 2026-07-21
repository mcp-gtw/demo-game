import { TEXT_DPR } from "../constants.js";

// a crisp text object: high resolution so glyphs stay sharp over the pixel-art world.
export class Label {
    constructor(scene, options = {}) {
        const style = {
            fontFamily: "Roboto, sans-serif",
            fontSize: options.size ?? "16px",
            fontStyle: options.weight ?? "700",
            color: options.color ?? "#ffffff",
        };

        if (options.stroke) {
            style.stroke = options.stroke;
            style.strokeThickness = options.strokeThickness ?? 4;
        }

        this.text = scene.add.text(options.x ?? 0, options.y ?? 0, options.text ?? "", style);
        this.text.setResolution(TEXT_DPR);
        this.text.setOrigin(options.originX ?? 0, options.originY ?? 0);

        if (options.lineSpacing) {
            this.text.setLineSpacing(options.lineSpacing);
        }
    }

    setText(value) {
        this.text.setText(value);
        return this;
    }
}
