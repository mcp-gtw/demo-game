import { latencyLevel, statusLine } from "../helpers/format.js";
import { Label } from "./Label.js";
import { Panel } from "./Panel.js";
import { INK, LATENCY_COLOR, STATUS_COLOR } from "../constants.js";

const HEIGHT = 52;
const PAD_LEFT = 38;
const PAD_RIGHT = 20;

// a parchment strip showing the connection dot, its label, the latency and the online count. The
// panel grows to fit the label so a longer status never clips.
export class StatusStrip {
    constructor(scene) {
        this.x = 0;
        this.y = 0;
        this.panel = new Panel(scene, PAD_LEFT + PAD_RIGHT, HEIGHT);
        this.dot = scene.add.circle(0, 0, 6, STATUS_COLOR.connecting);
        this.label = new Label(scene, { size: "16px", color: INK, originY: 0.5 });
        this.root = scene.add.container(0, 0).add([this.panel.node, this.dot, this.label.text]);
    }

    update(status, latencyMs, online) {
        const color = status === "online" ? LATENCY_COLOR[latencyLevel(latencyMs)] : STATUS_COLOR[status];
        this.dot.setFillStyle(color);
        this.label.setText(statusLine(status, latencyMs, online));
        this.#reflow();
    }

    layout(x, y) {
        this.x = x;
        this.y = y;
        this.#reflow();
    }

    #reflow() {
        this.width = PAD_LEFT + Math.ceil(this.label.text.width) + PAD_RIGHT;
        this.panel.setSize(this.width, HEIGHT).setPosition(this.x, this.y);
        this.dot.setPosition(this.x + 22, this.y + HEIGHT / 2);
        this.label.text.setPosition(this.x + PAD_LEFT, this.y + HEIGHT / 2);
    }

    get bottom() {
        return HEIGHT;
    }
}
