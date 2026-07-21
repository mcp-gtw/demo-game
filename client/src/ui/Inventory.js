import { Label } from "./Label.js";
import { Panel } from "./Panel.js";
import { INK, RESOURCE_ICONS } from "../constants.js";

const HEIGHT = 52;
const ICON = 30;
const PAD = 22;
const GAP_ICON = 8;
const GAP_CHIP = 26;

// a parchment strip of resource chips (icon plus count). The panel grows to fit the chips so large
// counts never clip.
export class Inventory {
    constructor(scene) {
        this.x = 0;
        this.y = 0;
        this.panel = new Panel(scene, PAD * 2, HEIGHT);
        this.icons = {};
        this.counts = {};
        this.root = scene.add.container(0, 0).add(this.panel.node);

        for (const [key, texture] of RESOURCE_ICONS) {
            this.icons[key] = scene.add.image(0, 0, texture).setDisplaySize(ICON, ICON);
            this.counts[key] = new Label(scene, { size: "18px", color: INK, originY: 0.5 });
            this.root.add([this.icons[key], this.counts[key].text]);
        }
    }

    update(entity) {
        const resources = entity?.resources ?? {};

        for (const [key] of RESOURCE_ICONS) {
            this.counts[key].setText(String(resources[key] ?? 0));
        }

        this.#reflow();
    }

    layout(x, y) {
        this.x = x;
        this.y = y;
        this.#reflow();
    }

    #reflow() {
        const midY = this.y + HEIGHT / 2;
        let cx = this.x + PAD;

        for (const [key] of RESOURCE_ICONS) {
            this.icons[key].setPosition(cx + ICON / 2, midY);
            const textX = cx + ICON + GAP_ICON;
            this.counts[key].text.setPosition(textX, midY);
            cx = textX + Math.ceil(this.counts[key].text.width) + GAP_CHIP;
        }

        this.width = cx - GAP_CHIP + PAD - this.x;
        this.panel.setSize(this.width, HEIGHT).setPosition(this.x, this.y);
    }

    get bottom() {
        return HEIGHT;
    }
}
