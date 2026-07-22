import Phaser from "phaser";
import { angleOf, animForState, cellCenter, facesLeft } from "../helpers/geometry.js";
import { healthRatio } from "../helpers/health.js";
import { ENEMY_COLOR, TEXT_DPR, TREES, UNITS } from "../constants.js";

// a jump beyond this many cells is a teleport (respawn), so the sprite snaps instead of sliding
const TELEPORT_CELLS = 2;

// vertical offsets in tiles for the labels above a unit, stacked so they never overlap: the health
// bar sits just above the head, the name above the bar, the speech bubble above the name
const BAR_OFFSET = -1.15;
const NAME_OFFSET = -1.45;
const BUBBLE_OFFSET = -1.9;

// one on-screen entity: a container holding its animated body plus a name tag, health bar and
// speech bubble. It owns nothing but drawing, reading each frame's interpolated entity data.
export class EntityView {
    constructor(scene, entity, tile, playerId) {
        this.scene = scene;
        this.tile = tile;
        this.playerId = playerId;
        this.kind = entity.kind;
        // collectibles lie flat on the ground, so they render in a band strictly below every actor
        this.groundBand = (scene.map.rows + 1) * tile;
        this.container = scene.add.container(0, 0);
        this.extras = {};
        this.body = this.#createBody(entity);
    }

    #createBody(entity) {
        if (entity.kind === "player" || entity.kind === "enemy") {
            return this.#createUnit(entity);
        }

        if (entity.kind === "projectile") {
            return this.#createProjectile(entity);
        }

        if (entity.kind === "tree") {
            return this.#createTree(entity);
        }

        if (entity.kind === "coin") {
            return this.#createStatic("coin");
        }

        return this.#createStatic(entity.kind === "food" ? "meat" : `item_${entity.item}`);
    }

    #createUnit(entity) {
        const unit = UNITS[this.#unitKey(entity)];
        const sprite = this.scene.add.sprite(0, 0, `${this.#textureBase(entity)}_idle`);
        sprite.setOrigin(0.5, unit.originY).setScale((this.tile * unit.scale) / unit.frame);
        this.container.add(sprite);

        if (entity.kind === "player") {
            const own = entity.id === this.playerId;
            const name = this.scene.add.text(0, this.tile * NAME_OFFSET, entity.name, {
                fontFamily: "Roboto, sans-serif",
                fontSize: "16px",
                fontStyle: "700",
                color: own ? "#fff2c2" : "#e6f2ff",
                stroke: "#12182b",
                strokeThickness: 5,
            });
            name.setOrigin(0.5, 1).setResolution(TEXT_DPR);
            this.container.add(name);
        }

        this.extras.bar = this.scene.add.graphics();
        this.container.add(this.extras.bar);
        return sprite;
    }

    // the texture-key base for this unit: a colored class sprite in the player's color or enemy red,
    // or the bare key for an uncolored animal
    #textureBase(entity) {
        const key = this.#unitKey(entity);

        if (!UNITS[key].colored) {
            return key;
        }

        return `${entity.kind === "enemy" ? ENEMY_COLOR : entity.color}_${key}`;
    }

    #createProjectile(entity) {
        const sprite = this.scene.add.image(0, 0, entity.hostile ? "arrow_enemy" : "arrow_player");
        sprite.setScale((this.tile * 0.7) / sprite.width);
        this.container.add(sprite);
        return sprite;
    }

    #createTree(entity) {
        this.tree = TREES[(entity.position.x * 7 + entity.position.y * 13) % TREES.length];
        const sprite = this.scene.add.sprite(0, 0, this.tree.key);
        sprite.setOrigin(0.5, this.tree.originY).setScale((this.tile * this.tree.scale) / this.tree.frameWidth);
        sprite.play(`${this.tree.key}_sway`);
        this.container.add(sprite);
        return sprite;
    }

    #createStatic(texture) {
        const sprite = this.scene.add.image(0, 0, texture);
        sprite.setScale((this.tile * 0.7) / sprite.width);
        this.container.add(sprite);

        // a fresh drop (loot or a respawned pickup) hops in, while items already on the map at load
        // simply appear
        if (this.scene.primed) {
            this.#dropIn(sprite);
        }

        return sprite;
    }

    #dropIn(sprite) {
        const rest = sprite.scaleX;
        sprite.setScale(rest * 0.4);
        sprite.y = -this.tile * 0.85;
        this.scene.tweens.add({ targets: sprite, y: 0, duration: 420, ease: "Bounce.Out" });
        this.scene.tweens.add({ targets: sprite, scaleX: rest, scaleY: rest, duration: 240, ease: "Back.Out" });
    }

    update(entity, now, delta) {
        const y = this.#place(entity, delta);

        if (this.kind === "player" || this.kind === "enemy") {
            this.#animateUnit(entity, now);
        } else if (this.kind === "tree") {
            this.#updateTree(entity);
        } else if (this.kind === "projectile") {
            this.body.setRotation(angleOf(entity.facing));
            this.#trail(entity);
        }

        this.container.setDepth(this.#depth(entity, y));
        this.#hitFlash(entity);
    }

    // actors walk smoothly toward their authoritative cell over their move duration, so a slow enemy
    // slides between tiles instead of popping. Everything else follows the snapshot interpolation.
    #place(entity, delta) {
        if (this.kind !== "player" && this.kind !== "enemy") {
            this.container.setPosition(entity.px, entity.py);
            return entity.py;
        }

        const target = cellCenter(entity.position, this.tile);
        const dx = target.x - (this.renderX ?? target.x);
        const dy = target.y - (this.renderY ?? target.y);
        const distance = Math.hypot(dx, dy);
        const teleport = this.renderX === undefined || distance > this.tile * TELEPORT_CELLS;

        if (teleport || distance < 0.01) {
            this.renderX = target.x;
            this.renderY = target.y;
        } else {
            const speed = this.tile / entity.moveMs;
            const advance = Math.min(distance, speed * delta);
            this.renderX += (dx / distance) * advance;
            this.renderY += (dy / distance) * advance;
        }

        this.container.setPosition(this.renderX, this.renderY);
        return this.renderY;
    }

    #depth(entity, y) {
        if (entity.kind === "projectile") {
            return y + 5000;
        }

        if (entity.kind === "food" || entity.kind === "item" || entity.kind === "coin") {
            return y - this.groundBand;
        }

        return y;
    }

    #hitFlash(entity) {
        if (entity.health != null && this.lastHealth != null && entity.health < this.lastHealth) {
            this.#flashTint();
            this.scene.damageNumbers?.spawn(this.container.x, this.container.y, this.lastHealth - entity.health, "#ff5a4a");
        }

        this.lastHealth = entity.health;
    }

    #flashTint() {
        this.body.setTint(0xff3b30).setTintMode(Phaser.TintModes.FILL);
        this.flashTimer?.remove();
        this.flashTimer = this.scene.time.delayedCall(90, () => {
            this.body.setTintMode(Phaser.TintModes.MULTIPLY).clearTint();
        });
    }

    #trail(entity) {
        // stream the trail from the arrow's tail so it never sits on top of the shaft
        const back = this.tile * 0.34;
        const angle = angleOf(entity.facing);
        const x = entity.px - Math.cos(angle) * back;
        const y = entity.py - Math.sin(angle) * back;
        const dot = this.scene.add.circle(x, y, this.tile * 0.035, 0xfff2b0, 0.7);
        dot.setDepth(entity.py + 4000);
        this.scene.tweens.add({ targets: dot, alpha: 0, scale: 0, duration: 260, onComplete: () => dot.destroy() });
    }

    #updateTree(entity) {
        if (this.lastHits != null && entity.hits < this.lastHits) {
            this.#flashTint();
            this.scene.damageNumbers?.spawn(this.container.x, this.container.y, this.lastHits - entity.hits, "#ffce54");
        }

        this.lastHits = entity.hits;

        const wanted = entity.broken ? "stump" : this.tree.key;

        if (this.body.texture.key === wanted) {
            return;
        }

        if (entity.broken) {
            this.body.setTexture("stump").stop();
        } else {
            this.body.setTexture(this.tree.key).play(`${this.tree.key}_sway`);
        }
    }

    #animateUnit(entity, now) {
        this.body.play(`${this.#textureBase(entity)}_${animForState(entity.state)}`, true);
        this.body.setFlipX(facesLeft(entity.facing));
        this.container.setAlpha(this.#alpha(entity, now));
        this.#drawHealth(entity);
        this.#speech(entity);
    }

    #drawHealth(entity) {
        const bar = this.extras.bar;
        bar.clear();

        if (entity.health >= entity.maxHealth) {
            return;
        }

        const width = this.tile * 0.9;
        const ratio = healthRatio(entity.health, entity.maxHealth);
        const y = this.tile * BAR_OFFSET;
        bar.fillStyle(0x10152b, 0.85).fillRect(-width / 2, y, width, 6);
        bar.fillStyle(entity.kind === "player" ? 0x62c462 : 0xe06a5a, 1);
        bar.fillRect(-width / 2, y, width * ratio, 6);
    }

    #speech(entity) {
        if (!entity.speech) {
            this.extras.bubble?.destroy();
            this.extras.bubble = null;
            return;
        }

        if (this.extras.bubbleText === entity.speech && this.extras.bubble) {
            return;
        }

        this.extras.bubble?.destroy();
        const text = this.scene.add.text(0, this.tile * BUBBLE_OFFSET, entity.speech, {
            fontFamily: "Roboto, sans-serif",
            fontSize: "12px",
            color: "#3a2a14",
            backgroundColor: "#f4ead2",
            padding: { x: 7, y: 4 },
        });
        text.setOrigin(0.5, 1).setResolution(TEXT_DPR);
        this.container.add(text);
        this.extras.bubble = text;
        this.extras.bubbleText = entity.speech;
    }

    #alpha(entity, now) {
        if (!entity.alive) {
            return 0.3;
        }

        if (entity.immune && Math.floor(now / 120) % 2 === 0) {
            return 0.35;
        }

        return 1;
    }

    #unitKey(entity) {
        if (entity.kind === "player") {
            return entity.sprite;
        }

        return this.scene.enemySprites[entity.name];
    }

    destroy() {
        this.flashTimer?.remove();
        this.container.destroy();
    }
}
