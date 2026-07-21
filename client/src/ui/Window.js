import Phaser from "phaser";
import { DPR, INK, INK_SOFT, TEXT_DPR } from "../constants.js";
import { Button } from "./Button.js";
import { CopyButton } from "./CopyButton.js";
import { Panel } from "./Panel.js";

const PAD = 30;
const TITLE_GAP = 16;
const COPY_GAP = 18;
const SCREEN_MARGIN = 20;
const MAX_PANEL_WIDTH = 560;
const MAX_BODY_HEIGHT = 440;
const MONO = "ui-monospace, Menlo, monospace";

// a closable parchment window sized to its content but capped to the viewport. A body taller than
// the space left is shown one page of wrapped lines at a time and scrolled with the mouse wheel, so
// it never spills off screen and needs no mask. Re-lays-out on resize to stay centred.
export class Window {
    constructor(scene, { title, body, mono = false, copyable = false }) {
        this.scene = scene;
        this.body = body;
        this.offset = 0;
        this.root = scene.add.container(0, 0).setScale(DPR).setDepth(150000);

        this.backdrop = scene.add.rectangle(0, 0, 10, 10, 0x0a0f1a, 0.55).setOrigin(0).setInteractive();
        this.backdrop.on("pointerdown", (pointer) => this.#onBackdrop(pointer));
        this.panel = new Panel(scene, 10, 10);
        this.title = scene.add
            .text(0, 0, title, { fontFamily: "Roboto, sans-serif", fontSize: "22px", fontStyle: "800", color: INK })
            .setResolution(TEXT_DPR);
        this.text = scene.add
            .text(0, 0, "", {
                fontFamily: mono ? MONO : "Roboto, sans-serif",
                fontSize: mono ? "14px" : "16px",
                color: INK_SOFT,
                lineSpacing: 5,
                wordWrap: { width: 400 },
            })
            .setResolution(TEXT_DPR);
        this.copy = copyable ? new CopyButton(scene, () => body) : null;
        this.closeButton = new Button(scene, { size: 40, iconSize: 22, icon: "icon_close", onClick: () => this.close() });

        this.root.add([this.backdrop, this.panel.node, this.title, this.text, this.closeButton.root]);
        if (this.copy) {
            this.root.add(this.copy.root);
        }

        this.onWheel = (_pointer, _over, _dx, dy) => this.#scroll(Math.sign(dy));
        this.onShutdown = () => this.close();
        this.#layout();
        scene.scale.on("resize", this.#layout, this);
        scene.input.on("wheel", this.onWheel);
        scene.events.once("shutdown", this.onShutdown);
    }

    #layout() {
        const width = this.scene.scale.gameSize.width / DPR;
        const height = this.scene.scale.gameSize.height / DPR;
        this.backdrop.setSize(width, height);
        this.backdrop.input.hitArea.setTo(0, 0, width, height);

        const panelWidth = Math.max(220, Math.min(MAX_PANEL_WIDTH, width - SCREEN_MARGIN * 2));
        const bodyWidth = Math.max(60, panelWidth - PAD * 2);

        // advanced wrap so an unbreakable token (a url or a long token) breaks to fit instead of spilling
        this.title.setWordWrapWidth(bodyWidth, true);
        this.text.setWordWrapWidth(bodyWidth, true);

        this.lines = this.text.getWrappedText(this.body);
        this.text.setText(this.lines.join("\n"));
        const lineHeight = this.text.height / this.lines.length;

        const headFoot = PAD * 2 + this.title.height + TITLE_GAP + (this.copy ? COPY_GAP + this.copy.height : 0);
        const maxBodyHeight = Math.min(height - SCREEN_MARGIN * 2 - headFoot, MAX_BODY_HEIGHT);
        this.pageLines = Math.max(1, Math.min(this.lines.length, Math.floor(maxBodyHeight / lineHeight)));
        this.offset = Math.max(0, Math.min(this.offset, this.lines.length - this.pageLines));
        this.#renderPage();

        const panelHeight = headFoot + this.pageLines * lineHeight;
        const originX = (width - panelWidth) / 2;
        const originY = (height - panelHeight) / 2;

        this.panelRect = {
            left: originX * DPR,
            top: originY * DPR,
            right: (originX + panelWidth) * DPR,
            bottom: (originY + panelHeight) * DPR,
        };

        this.panel.setSize(panelWidth, panelHeight).setPosition(originX, originY);
        this.title.setPosition(originX + PAD, originY + PAD);
        this.text.setPosition(originX + PAD, originY + PAD + this.title.height + TITLE_GAP);
        this.closeButton.setPosition(originX + panelWidth - 22, originY + 22);

        if (this.copy) {
            this.copy.setPosition(originX + PAD + this.copy.width / 2, originY + panelHeight - PAD - this.copy.height / 2);
        }
    }

    #renderPage() {
        this.text.setText(this.lines.slice(this.offset, this.offset + this.pageLines).join("\n"));
    }

    // dismiss only when the click lands outside the panel, so reading or selecting body text never closes it
    #onBackdrop(pointer) {
        const rect = this.panelRect;
        const inside =
            pointer.x >= rect.left &&
            pointer.x <= rect.right &&
            pointer.y >= rect.top &&
            pointer.y <= rect.bottom;

        if (!inside) {
            this.close();
        }
    }

    #scroll(delta) {
        const max = Math.max(0, this.lines.length - this.pageLines);
        const next = Phaser.Math.Clamp(this.offset + delta, 0, max);

        if (next !== this.offset) {
            this.offset = next;
            this.#renderPage();
        }
    }

    close() {
        if (this.destroyed) {
            return;
        }

        this.destroyed = true;
        this.scene.scale.off("resize", this.#layout, this);
        this.scene.input.off("wheel", this.onWheel);
        this.scene.events.off("shutdown", this.onShutdown);
        this.root.destroy();
    }
}
