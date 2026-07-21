import { statRows } from "../helpers/format.js";
import { Label } from "./Label.js";
import { Panel } from "./Panel.js";
import { INK, INK_SOFT } from "../constants.js";

const CONTENT_TOP = 58;
const CONTENT_PADDING = 24;
const COLUMN_GUTTER = 26;

// the parchment character sheet: a titled window with a close button and two text columns. The value
// column sits just past the longest label and both columns scale together to fit the panel, so a long
// value can never overlap its label nor spill past the edge.
export class StatsWindow {
    constructor(scene, onClose) {
        this.root = scene.add.container(0, 0).setVisible(false);
        this.panel = new Panel(scene, 340, 430);
        this.title = new Label(scene, { x: 24, y: 20, size: "17px", color: INK });
        this.title.setText("YOUR CHARACTER");
        this.close = scene.add
            .image(0, 0, "icon_close")
            .setDisplaySize(30, 30)
            .setOrigin(1, 0)
            .setInteractive({ useHandCursor: true });
        this.close.on("pointerup", () => onClose());

        this.content = scene.add.container(CONTENT_PADDING, CONTENT_TOP);
        this.labels = new Label(scene, { size: "15px", color: INK, lineSpacing: 9 });
        this.values = new Label(scene, { size: "15px", color: INK_SOFT, lineSpacing: 9 });
        this.content.add([this.labels.text, this.values.text]);

        this.root.add([this.panel.node, this.title.text, this.close, this.content]);
    }

    setVisible(visible) {
        this.root.setVisible(visible);
    }

    get visible() {
        return this.root.visible;
    }

    update(player) {
        const rows = statRows(player);
        this.labels.setText(rows.map((row) => row[0]).join("\n"));
        this.values.setText(rows.map((row) => row[1]).join("\n"));
        this.#fitContent();
    }

    layout(x, y, width, height) {
        this.panel.setSize(width, height);
        this.root.setPosition(x, y);
        this.close.setPosition(width - 16, 16);
        this.panelWidth = width;
        this.panelHeight = height;
        this.#fitContent();
    }

    // place the value column past the longest label, then scale both columns down together until the
    // whole block fits the panel in width and height
    #fitContent() {
        if (!this.panelWidth || !this.panelHeight) return;

        this.content.setScale(1);
        this.values.text.setX(this.labels.text.width + COLUMN_GUTTER);

        const naturalWidth = this.values.text.x + this.values.text.width;
        const naturalHeight = Math.max(this.labels.text.height, this.values.text.height);
        const availableWidth = this.panelWidth - CONTENT_PADDING * 2;
        const availableHeight = this.panelHeight - CONTENT_TOP - CONTENT_PADDING;
        const scale = Math.min(1, availableWidth / naturalWidth, availableHeight / naturalHeight);

        this.content.setScale(scale);
    }
}
