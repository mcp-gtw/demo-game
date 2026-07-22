import Phaser from "phaser";
import { Clouds } from "../game/Clouds.js";
import { claudeCommand, mcpJson } from "../helpers/mcp.js";
import { DPR, INK, INK_SOFT, TEXT_DPR } from "../constants.js";
import { Panel } from "../ui/Panel.js";
import { TextButton } from "../ui/TextButton.js";
import { Window } from "../ui/Window.js";

const MAX_CARD_WIDTH = 440;
const MIN_CARD_WIDTH = 200;
const SCREEN_MARGIN = 16;
const PAD = 28;
const GAP = 12;
const MIN_BUTTON_WIDTH = 200;

// the Phaser landing: an island background with drifting clouds and a parchment card. Login reveals
// the connect options as buttons, each opening a closable window. No DOM, everything is drawn here.
export class LoginScene extends Phaser.Scene {
    constructor() {
        super("login");
    }

    init(data) {
        this.store = data.store;
        this.revealed = false;
        this.enabled = false;
    }

    create() {
        for (const key of ["cloud1", "cloud2", "cloud3"]) {
            this.textures.get(key).setFilter(Phaser.Textures.FilterMode.NEAREST);
        }

        this.bg = this.add.image(0, 0, "login_bg").setOrigin(0.5).setDepth(-100);

        const cloudLayer = this.add.container(0, 0).setScale(DPR).setDepth(50);
        const width = this.scale.gameSize.width / DPR;
        const height = this.scale.gameSize.height / DPR;
        const bounds = { minX: -160, maxX: width + 160, minY: 20, maxY: height - 40 };
        const scale = { min: 0.4, max: 0.85 };
        const speed = { min: 14, max: 34 };
        this.clouds = new Clouds(this, { layer: cloudLayer, bounds, count: 5, scale, speed });

        this.uiLayer = this.add.container(0, 0).setScale(DPR).setDepth(100000);
        this.card = this.add.container(0, 0);
        this.uiLayer.add(this.card);
        this.panel = new Panel(this, MAX_CARD_WIDTH, 260);
        this.title = this.#text("MCP BATTLE", { size: "40px", weight: "800", color: INK }).setOrigin(0.5, 0);
        this.online = this.#text("… players online", { size: "16px", color: INK_SOFT }).setOrigin(0.5, 0);
        this.status = this.#text("Connecting…", { size: "15px", color: INK_SOFT }).setOrigin(0.5, 0);
        this.card.add([this.panel.node, this.title, this.online, this.status]);

        this.loginButton = new TextButton(this, { text: "Login", size: "20px", onClick: () => this.#reveal() });
        this.card.add(this.loginButton.root);

        this.optionButtons = [];
        this.#layout();
        this.scale.on("resize", this.#layout, this);
        this.events.once("shutdown", () => this.scale.off("resize", this.#layout, this));
    }

    update(_time, delta) {
        this.clouds.update(delta);
        this.online.setText(`${this.store.online} players online`);

        if (!this.enabled && this.store.session) {
            this.enabled = true;
            this.status.setText("Point your agent at the connect options, then it calls login.");
        }

        if (!this.enabled) {
            this.status.setText(this.store.status === "offline" ? "Reconnecting…" : "Connecting…");
        }
    }

    #reveal() {
        if (!this.enabled || this.revealed) {
            return;
        }

        this.revealed = true;
        const info = this.store.session;
        this.optionButtons = [
            new TextButton(this, {
                text: "Claude Code (CLI)",
                onClick: () => {
                    const command = claudeCommand(info.mcpUrl, info.mcpToken);
                    this.#open("Claude Code (CLI)", command, { mono: true, copies: [{ label: "Copy", value: command }] });
                },
            }),
            new TextButton(this, { text: "MCP Config (mcp.json)", onClick: () => this.#openMcp(info) }),
            new TextButton(this, { text: "Endpoint + Token", onClick: () => this.#openConnect(info) }),
            new TextButton(this, { text: "Tools", onClick: () => this.#openTools() }),
        ];

        this.loginButton.root.setVisible(false);

        for (const button of this.optionButtons) {
            this.card.add(button.root);
        }

        this.#layout();
    }

    #openMcp(info) {
        const json = mcpJson(info.mcpUrl, info.mcpToken);
        this.#open("MCP Config (mcp.json)", json, { mono: true, copies: [{ label: "Copy", value: json }] });
    }

    // the endpoint and token on their own, each with its own copy button, so pasting one never drags
    // the other along and breaks a config
    #openConnect(info) {
        const body = `Endpoint\n${info.mcpUrl}\n\nToken\n${info.mcpToken}`;
        this.#open("Endpoint + Token", body, {
            mono: true,
            copies: [
                { label: "Copy Endpoint", value: info.mcpUrl },
                { label: "Copy Token", value: info.mcpToken },
            ],
        });
    }

    #openTools() {
        const tools = this.store.tools;
        const body = tools.length
            ? tools.map((tool) => `• ${tool.name}\n   ${tool.description}`).join("\n\n")
            : "The tool list loads once your session is ready.";
        this.#open("Tools", body, {});
    }

    #open(title, body, { mono = false, copies = [] }) {
        this.window?.close();
        this.window = new Window(this, { title, body, mono, copies });
    }

    #text(value, options) {
        return this.add
            .text(0, 0, value, {
                fontFamily: "Roboto, sans-serif",
                fontSize: options.size,
                fontStyle: options.weight ?? "600",
                color: options.color,
                align: "center",
            })
            .setResolution(TEXT_DPR);
    }

    #layout() {
        const width = this.scale.gameSize.width / DPR;
        const height = this.scale.gameSize.height / DPR;

        this.clouds.bounds = { minX: -160, maxX: width + 160, minY: 20, maxY: height - 40 };
        this.#coverBackground();

        const cardWidth = Math.max(MIN_CARD_WIDTH, Math.min(MAX_CARD_WIDTH, width - SCREEN_MARGIN * 2));
        const inner = cardWidth - PAD * 2;
        const centre = cardWidth / 2;

        for (const text of [this.title, this.online, this.status]) {
            text.setWordWrapWidth(inner).setPosition(centre, 0);
        }

        const rows = this.revealed ? this.optionButtons : [this.loginButton];
        const natural = Math.max(MIN_BUTTON_WIDTH, ...rows.map((button) => button.naturalWidth));
        const buttonWidth = Math.min(inner, natural);

        let y = PAD;
        this.title.setY(y);
        y += this.title.height + GAP;
        this.online.setY(y);
        y += this.online.height + 4;
        this.status.setY(y);
        y += this.status.height + GAP + 6;

        for (const button of rows) {
            button.setWidth(buttonWidth).setPosition(centre, y + button.height / 2);
            y += button.height + GAP;
        }

        const cardHeight = y - GAP + PAD;
        this.panel.setSize(cardWidth, cardHeight);
        this.card.setPosition((width - cardWidth) / 2, (height - cardHeight) / 2);
    }

    #coverBackground() {
        const gw = this.scale.gameSize.width;
        const gh = this.scale.gameSize.height;
        const scale = Math.max(gw / this.bg.width, gh / this.bg.height);
        this.bg.setScale(scale).setPosition(gw / 2, gh / 2);
    }
}
