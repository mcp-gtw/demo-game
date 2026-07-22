import { DPR, INK, TEXT_DPR } from "../constants.js";

const PANEL_W = 340;
const PANEL_H = 128;
const BAR_H = 18;

// the loading screen shown while BootScene fetches assets. Drawn entirely with graphics + text so it
// needs no preloaded texture, and it lays out in logical coordinates inside a DPR-scaled layer.
export class LoadingWindow {
    constructor(scene) {
        this.scene = scene;
        this.progress = 0;
        this.layer = scene.add.container(0, 0).setScale(DPR).setDepth(999999);
        this.panel = scene.add.graphics();
        this.bar = scene.add.graphics();
        this.title = scene.add
            .text(0, 0, "Loading…", { fontFamily: "Roboto, sans-serif", fontSize: "22px", fontStyle: "800", color: INK })
            .setOrigin(0.5)
            .setResolution(TEXT_DPR);
        this.layer.add([this.panel, this.bar, this.title]);

        this.#render();
        scene.scale.on("resize", this.#render, this);
        scene.events.once("shutdown", () => {
            scene.scale.off("resize", this.#render, this);
            this.layer.destroy();
        });
    }

    update(progress) {
        this.progress = progress;
        this.title.setText(`Loading… ${Math.round(progress * 100)}%`);
        this.#render();
    }

    // swap to an error state when an asset fails to load, so a broken UI is never shown: a message and
    // a Reload button that fetches everything again
    showReload() {
        this.failed = true;
        this.bar.setVisible(false);
        this.title.setText("Couldn't load the game");
        this.hint = this.scene.add
            .text(0, 0, "Some assets failed to load.", { fontFamily: "Roboto, sans-serif", fontSize: "14px", color: INK })
            .setOrigin(0.5)
            .setResolution(TEXT_DPR);
        this.reload = this.scene.add
            .text(0, 0, "↻  Reload", { fontFamily: "Roboto, sans-serif", fontSize: "20px", fontStyle: "800", color: "#7a1f14" })
            .setOrigin(0.5)
            .setResolution(TEXT_DPR)
            .setInteractive({ useHandCursor: true })
            .on("pointerup", () => location.reload());
        this.layer.add([this.hint, this.reload]);
        this.#render();
    }

    #render() {
        const width = this.scene.scale.gameSize.width / DPR;
        const height = this.scene.scale.gameSize.height / DPR;
        const x = (width - PANEL_W) / 2;
        const y = (height - PANEL_H) / 2;

        this.panel.clear();
        this.panel.fillStyle(0x2b6a86, 1).fillRect(0, 0, width, height);
        this.panel.fillStyle(0xefe0c0, 1).fillRoundedRect(x, y, PANEL_W, PANEL_H, 14);
        this.panel.lineStyle(4, 0x2a1d10, 1).strokeRoundedRect(x, y, PANEL_W, PANEL_H, 14);

        if (this.failed) {
            this.title.setPosition(width / 2, y + 38);
            this.hint.setPosition(width / 2, y + 70);
            this.reload.setPosition(width / 2, y + 100);
            return;
        }

        this.title.setPosition(width / 2, y + 44);
        const barX = x + 30;
        const barY = y + 80;
        const barW = PANEL_W - 60;
        this.bar.clear();
        this.bar.fillStyle(0x2b2519, 1).fillRoundedRect(barX, barY, barW, BAR_H, 6);
        this.bar.fillStyle(0x62c462, 1).fillRoundedRect(barX, barY, Math.max(BAR_H, barW * this.progress), BAR_H, 6);
    }
}
