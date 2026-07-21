// a square image button (regular/pressed frames) with a centred icon and a click callback.
export class Button {
    constructor(scene, options) {
        this.size = options.size ?? 58;
        this.base = scene.add.image(0, 0, "btn").setDisplaySize(this.size, this.size);
        this.icon = scene.add
            .image(0, 0, options.icon)
            .setDisplaySize(options.iconSize ?? 34, options.iconSize ?? 34);
        this.base.setInteractive({ useHandCursor: true });
        this.base.on("pointerdown", () => this.base.setTexture("btn_down"));
        this.base.on("pointerout", () => this.base.setTexture("btn"));
        this.base.on("pointerup", () => {
            this.base.setTexture("btn");
            options.onClick?.();
        });
        this.root = scene.add.container(0, 0).add([this.base, this.icon]);
    }

    setPosition(x, y) {
        this.base.setPosition(x, y);
        this.icon.setPosition(x, y);
        return this;
    }
}
