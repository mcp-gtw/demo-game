import { copyText } from "../helpers/clipboard.js";
import { TextButton } from "./TextButton.js";

// a text button that copies a value to the clipboard and briefly confirms
export class CopyButton {
    constructor(scene, getValue) {
        this.getValue = getValue;
        this.button = new TextButton(scene, { text: "Copy", minWidth: 108, onClick: () => this.#copy() });
        this.root = this.button.root;
        this.width = this.button.width;
        this.height = this.button.height;

        // the confirm timer lives on the scene clock, so drop it when the button is torn down
        this.root.once("destroy", () => this.timer?.remove());
    }

    setPosition(x, y) {
        this.button.setPosition(x, y);
        return this;
    }

    async #copy() {
        await copyText(this.getValue());

        if (!this.root.active) {
            return;
        }

        this.button.setText("Copied");
        this.timer?.remove();
        this.timer = this.button.scene.time.delayedCall(1200, () => this.button.setText("Copy"));
    }
}
