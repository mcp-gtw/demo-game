import Phaser from "phaser";
import { selfEntity } from "../helpers/store.js";
import { Button } from "../ui/Button.js";
import { HealthBar } from "../ui/HealthBar.js";
import { DPR } from "../constants.js";
import { Inventory } from "../ui/Inventory.js";
import { StatsWindow } from "../ui/StatsWindow.js";
import { StatusStrip } from "../ui/StatusStrip.js";

const MARGIN = 18;

// the in-game hud: a parchment status strip, resource inventory, wooden health bar and a shield
// button that opens the parchment character sheet. Everything is drawn from the Tiny Swords art.
export class HudScene extends Phaser.Scene {
    constructor() {
        super("hud");
    }

    init(data) {
        this.store = data.store;
        this.lastMe = null;
    }

    create() {
        this.layer = this.add.container(0, 0).setScale(DPR);
        this.statusStrip = new StatusStrip(this);
        this.inventory = new Inventory(this);
        this.healthBar = new HealthBar(this);
        this.statsWindow = new StatsWindow(this, () => this.#toggleStats());
        this.statsButton = new Button(this, {
            icon: "icon_stats",
            onClick: () => this.#toggleStats(),
        });
        this.layer.add([
            this.statusStrip.root,
            this.inventory.root,
            this.healthBar.root,
            this.statsWindow.root,
            this.statsButton.root,
        ]);

        this.#layout();
        this.scale.on("resize", this.#layout, this);
        this.events.once("shutdown", () => this.scale.off("resize", this.#layout, this));
        this.time.addEvent({
            delay: 1500,
            loop: true,
            callback: () => this.statsWindow.visible && this.store.requestStats?.(),
        });
    }

    update() {
        // the connection indicator is independent of world state, so refresh it first and always
        this.statusStrip.update(this.store.status, this.store.latencyMs, this.store.online);

        const self = selfEntity(this.store);
        this.healthBar.update(self);
        this.inventory.update(self);

        if (this.statsWindow.visible && this.store.me !== this.lastMe) {
            this.lastMe = this.store.me;

            if (this.store.me) {
                this.statsWindow.update(this.store.me);
            }
        }
    }

    #layout() {
        const width = this.scale.gameSize.width / DPR;
        const height = this.scale.gameSize.height / DPR;

        this.statusStrip.layout(MARGIN, MARGIN);
        this.inventory.layout(MARGIN, MARGIN + this.statusStrip.bottom + 8);
        this.healthBar.layout(MARGIN, height - MARGIN - this.healthBar.height);

        const buttonX = width - MARGIN - 29;
        const buttonY = MARGIN + 29;
        this.statsButton.setPosition(buttonX, buttonY);

        const panelWidth = Math.max(1, Math.min(340, width - MARGIN * 2));
        const panelHeight = Math.max(1, Math.min(430, height - MARGIN * 2 - 70));
        this.statsWindow.layout(width - MARGIN - panelWidth, MARGIN + 70, panelWidth, panelHeight);
    }

    #toggleStats() {
        const open = !this.statsWindow.visible;
        this.statsWindow.setVisible(open);

        if (open) {
            this.store.requestStats?.();

            if (this.store.me) {
                this.statsWindow.update(this.store.me);
            }
        }
    }
}
