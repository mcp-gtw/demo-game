const VOLUME = 0.35;
const STORAGE_KEY = "mcp-game-muted";

// looping background track. Phaser unlocks WebAudio on the first user gesture, so the loop starts as
// soon as the page is interacted with. Pressing M toggles mute and remembers the choice.
export class Music {
    constructor(scene) {
        this.sound = scene.sound.add("music", { loop: true, volume: VOLUME });
        this.muted = localStorage.getItem(STORAGE_KEY) === "1";
        this.sound.play();
        this.sound.setMute(this.muted);
        scene.input.keyboard.on("keydown-M", () => this.toggle());
    }

    toggle() {
        this.muted = !this.muted;
        this.sound.setMute(this.muted);
        localStorage.setItem(STORAGE_KEY, this.muted ? "1" : "0");
    }
}
