import Phaser from "phaser";
import { buildAnimations } from "../helpers/animations.js";
import { Button } from "../ui/Button.js";
import { DPR, FOAM, FOAM_FRAME, INK, TEXT_DPR } from "../constants.js";
import { EntityView } from "../game/EntityView.js";
import { HealthBar } from "../ui/HealthBar.js";
import { Panel } from "../ui/Panel.js";
import { TextButton } from "../ui/TextButton.js";

const ROW = 96;
const LABEL_X = 30;
const ITEM_X = 360;

// a scrollable showcase (open /?gallery) rendering one of each element stacked vertically, so the
// look of every component and sprite can be checked at a glance. Reachable via make run.
export class GalleryScene extends Phaser.Scene {
    constructor() {
        super("gallery");
    }

    create() {
        buildAnimations(this);
        this.#makeSpark();
        this.cameras.main.setBackgroundColor("#2b6a86");
        this.layer = this.add.container(0, 0).setScale(DPR);
        this.y = 40;

        // minimal scene context so a real EntityView can be rendered in the player-card showcase
        this.playerId = "hero";
        this.map = { rows: 12 };
        this.enemySprites = {};

        this.#caption("Label", () => this.#label("The quick brown fox", "22px"));
        this.#caption("TextButton", () => this.layer.add(new TextButton(this, { text: "Press me" }).setPosition(ITEM_X + 70, this.y).root));
        this.#caption("Icon Button", () => this.layer.add(new Button(this, { icon: "icon_stats" }).setPosition(ITEM_X + 30, this.y).root));
        this.#caption("HealthBar", () => this.#healthBar());
        this.#caption("Panel", () => this.#panel());
        this.#caption("Warrior (blue) idle/run/attack", () => this.#unitCycle("blue_warrior"));
        this.#caption("Archer (yellow) idle/run/attack", () => this.#unitCycle("yellow_archer"));
        this.#caption("Monk (purple) idle/run/attack", () => this.#unitCycle("purple_monk"));
        this.#caption("Lancer (black) idle/run/attack", () => this.#unitCycle("black_lancer"));
        this.#caption("Enemy warrior (red) idle/run/attack", () => this.#unitCycle("red_warrior"));
        this.#caption("Sheep idle", () => this.#unit("sheep", "idle"));
        this.#playerCardRow();
        this.#caption("Tree", () => this.#tree());
        this.#caption("Projectile + trail", () => this.#arrow());
        this.#caption("Particles", () => this.#particles());
        this.#caption("Coastline foam (all borders)", () => this.#coastline());

        this.input.on("wheel", (_p, _o, _dx, dy) => {
            this.cameras.main.scrollY = Math.max(0, this.cameras.main.scrollY + dy * 0.6);
        });
    }

    #caption(text, build) {
        this.#label(text, "15px", LABEL_X, "#dfeefc");
        build();
        this.y += ROW;
    }

    #label(text, size, x = ITEM_X, color = INK) {
        const label = this.add
            .text(x, this.y, text, { fontFamily: "Roboto, sans-serif", fontSize: size, fontStyle: "700", color })
            .setOrigin(0, 0.5)
            .setResolution(TEXT_DPR);
        this.layer.add(label);
        return label;
    }

    #healthBar() {
        const bar = new HealthBar(this);
        bar.update({ name: "Hero", health: 68, maxHealth: 100 });
        bar.layout(ITEM_X, this.y - 20);
        this.layer.add(bar.root);
    }

    #panel() {
        const panel = new Panel(this, 220, 70);
        panel.setPosition(ITEM_X, this.y - 34);
        this.layer.add(panel.node);
    }

    #unit(key, state) {
        const sprite = this.add.sprite(ITEM_X + 40, this.y, `${key}_idle`).play(`${key}_${state}`);
        this.layer.add(sprite);
        return sprite;
    }

    #playerCardRow() {
        // a real EntityView so the framed health bar, the hit flash and a max-length speech bubble can
        // be tested live
        this.y += 110;
        this.#label("Player: name, bar, hit flash, speech", "15px", LABEL_X, "#dfeefc");

        const tile = 56;
        const cx = ITEM_X + 60;
        const hero = {
            id: "hero", kind: "player", name: "Hero", sprite: "warrior", color: "blue",
            state: "idle", facing: "down", health: 62, maxHealth: 100, alive: true, immune: false,
            position: { x: (cx - tile / 2) / tile, y: (this.y - tile / 2) / tile },
            moveMs: 280, speech: "The quick brown fox jumps over the lazy dog today!",
            visionRange: null, visionPulseSeq: 0,
        };
        const view = new EntityView(this, hero, tile, this.playerId);
        view.update(hero, this.time.now, 16);
        this.layer.add(view.container);

        // pulse damage so the framed bar drops and the hit flash reddens the sprite on a loop
        this.time.addEvent({
            delay: 1300,
            loop: true,
            callback: () => {
                hero.health = hero.health > 22 ? hero.health - 20 : 100;
                view.update(hero, this.time.now, 16);
            },
        });

        this.y += 130;
    }

    #unitCycle(key) {
        const sprite = this.#unit(key, "idle");
        const states = ["idle", "run", "attack"];
        let index = 0;
        this.time.addEvent({
            delay: 1100,
            loop: true,
            callback: () => {
                index = (index + 1) % states.length;
                sprite.play(`${key}_${states[index]}`);
            },
        });
    }

    #tree() {
        const tree = this.add.sprite(ITEM_X + 40, this.y, "tree0").setScale(0.35).play("tree0_sway");
        this.layer.add(tree);
    }

    #arrow() {
        const arrow = this.add.image(ITEM_X, this.y, "arrow_player").setScale(0.8);
        this.layer.add(arrow);
        this.tweens.add({
            targets: arrow,
            x: ITEM_X + 220,
            duration: 900,
            yoyo: true,
            repeat: -1,
            onUpdate: () => {
                const dot = this.add.circle(arrow.x - 22, arrow.y, 2, 0xfff2b0, 0.6);
                this.layer.add(dot);
                this.tweens.add({ targets: dot, alpha: 0, duration: 240, onComplete: () => dot.destroy() });
            },
        });
    }

    #particles() {
        const emit = () => {
            const burst = this.add.particles(ITEM_X + 40, this.y, "spark", {
                speed: { min: 40, max: 150 },
                angle: { min: 0, max: 360 },
                scale: { start: 0.5, end: 0 },
                alpha: { start: 0.9, end: 0 },
                lifespan: 500,
                tint: 0xbfe9ff,
                emitting: false,
            });
            this.layer.add(burst);
            burst.explode(14);
            this.time.delayedCall(700, () => burst.destroy());
        };
        emit();
        this.time.addEvent({ delay: 1300, loop: true, callback: emit });
    }

    #coastline() {
        // a 5x5 patch: a 3x3 grass block ringed by sea, foam rendered exactly like the game so the
        // coastline can be eyeballed without entering a match
        const t = 40;
        const cols = 5;
        const rows = 5;
        const box = this.add.container(ITEM_X, this.y - 12);
        box.add(this.add.tileSprite(0, 0, cols * t, rows * t, "water").setOrigin(0));

        const land = (c, r) => c >= 1 && c <= cols - 2 && r >= 1 && r <= rows - 2;
        const landDir = (c, r) => {
            let dx = 0;
            let dy = 0;
            for (const [nx, ny] of [[c + 1, r], [c - 1, r], [c, r + 1], [c, r - 1]]) {
                if (land(nx, ny)) {
                    dx += nx - c;
                    dy += ny - r;
                }
            }
            const len = Math.hypot(dx, dy);
            return len ? { x: dx / len, y: dy / len } : null;
        };

        for (let r = 0; r < rows; r += 1) {
            for (let c = 0; c < cols; c += 1) {
                const toward = land(c, r) ? null : landDir(c, r);

                if (!toward) {
                    continue;
                }

                const x = c * t + t / 2 + toward.x * t * FOAM.offset;
                const y = r * t + t / 2 + toward.y * t * FOAM.offset;
                box.add(
                    this.add
                        .sprite(x, y, "foam")
                        .setScale((t * FOAM.scale) / FOAM_FRAME)
                        .setAlpha(FOAM.alpha)
                        .play("foam_drift"),
                );
            }
        }

        for (let r = 1; r <= rows - 2; r += 1) {
            for (let c = 1; c <= cols - 2; c += 1) {
                box.add(this.add.rectangle(c * t + t / 2, r * t + t / 2, t, t, 0x86b64a));
            }
        }

        this.layer.add(box);
        this.y += rows * t - ROW + 24;
    }

    #makeSpark() {
        const graphics = this.make.graphics({ x: 0, y: 0, add: false });
        graphics.fillStyle(0xffffff, 1).fillCircle(8, 8, 8);
        graphics.generateTexture("spark", 16, 16);
        graphics.destroy();
    }
}
