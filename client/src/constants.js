// shared constants for the client: ui theme, texture manifests and render tuning.

// render at the device's physical pixels (capped) so text and art stay crisp on retina screens
export const DPR = Math.min(window.devicePixelRatio || 1, 2);

export const PANEL_BORDER = 20;
export const INK = "#463218";
export const INK_SOFT = "#5c4a2e";
export const STATUS_COLOR = { connecting: 0xf0c04a, offline: 0xe06a5a };
export const LATENCY_COLOR = { good: 0x62c462, fair: 0xf0c04a, poor: 0xe06a5a, unknown: 0x62c462 };
export const TEXT_DPR = DPR * 2;

// the faction skins shipped as full spritesheets per unit: players wear their chosen color, enemies
// are always red. A colored unit loads one sheet set per color under assets/units/<unit>/<color>/.
export const UNIT_COLORS = ["blue", "yellow", "purple", "black", "red"];
export const ENEMY_COLOR = "red";

// every unit sprite the client can draw: spritesheet frame size, on-screen scale in tiles, sprite
// origin (its feet sit at the cell centre) and per-animation frame rates. a missing attackRate means
// no attack animation (animals). colored units ship one sheet set per faction color, so a player
// renders as its class sprite in its chosen color and an enemy as its spec sprite in red.
export const UNITS = {
    warrior: { frame: 192, scale: 2.6, originY: 0.59, idleRate: 8, runRate: 12, attackRate: 12, colored: true },
    archer: { frame: 192, scale: 2.6, originY: 0.59, idleRate: 8, runRate: 12, attackRate: 14, colored: true },
    monk: { frame: 192, scale: 2.6, originY: 0.58, idleRate: 8, runRate: 12, attackRate: 12, colored: true },
    lancer: { frame: 320, scale: 4.3, originY: 0.62, idleRate: 8, runRate: 12, attackRate: 10, colored: true },
    sheep: { frame: 128, scale: 1.7, originY: 0.47, idleRate: 5, runRate: 6 },
};

// the texture-key bases a colored unit exposes (one per color), or its bare key when it has no colors
export function unitBases(key, unit) {
    return unit.colored ? UNIT_COLORS.map((color) => `${color}_${key}`) : [key];
}
// choppable tree variants, chosen per tree by its cell so a forest looks varied. each carries its
// spritesheet frame size, on-screen width in tiles and the origin that sits its trunk on the cell
export const TREES = [
    { key: "tree0", frameWidth: 192, frameHeight: 256, scale: 1.8, originY: 0.86 },
    { key: "tree1", frameWidth: 192, frameHeight: 256, scale: 1.8, originY: 0.86 },
    { key: "tree2", frameWidth: 192, frameHeight: 192, scale: 1.7, originY: 0.8 },
    { key: "tree3", frameWidth: 192, frameHeight: 192, scale: 1.7, originY: 0.8 },
];
export const FOAM_FRAME = 192;
// coastline foam tuning shared by the game and the gallery: each sea-edge foam is nudged this
// fraction of a cell onto the land (so the grass hides its inner half) and scaled to this many tiles
export const FOAM = { scale: 2.1, offset: 0.75, alpha: 0.75 };

export const OBJECT_TEXTURES = {
    castle: "assets/buildings/castle.png",
    house: "assets/buildings/house.png",
    tower: "assets/buildings/tower.png",
    rock1: "assets/decor/rock1.png",
    rock2: "assets/decor/rock2.png",
    rock3: "assets/decor/rock3.png",
    rock4: "assets/decor/rock4.png",
    bush1: "assets/decor/bush1.png",
    bush2: "assets/decor/bush2.png",
    bush3: "assets/decor/bush3.png",
    bush4: "assets/decor/bush4.png",
};

export const WORLD_TEXTURES = {
    arrow_player: "assets/units/archer/arrow.png",
    arrow_enemy: "assets/units/archer/arrow.png",
    water: "assets/terrain/water.png",
    stump: "assets/resources/stump.png",
    meat: "assets/resources/meat.png",
    coin: "assets/resources/coin.png",
    cloud1: "assets/decor/cloud1.png",
    cloud2: "assets/decor/cloud2.png",
    cloud3: "assets/decor/cloud3.png",
};

// clouds drift over the map area extended by this many cells on every side
export const CLOUD_MARGIN_CELLS = 8;
export const CLOUD_DENSITY_CELLS = 300;

export const MENU_TEXTURES = {
    login_bg: "assets/ui/login_bg.png",
    panel9: "assets/ui/panel9.png",
    btn: "assets/ui/button.png",
    btn_down: "assets/ui/button_pressed.png",
    icon_close: "assets/ui/icon_close.png",
};

export const HUD_TEXTURES = {
    hpbar: "assets/ui/hpbar.png",
    hpfill: "assets/ui/bar_fill.png",
    panel9: "assets/ui/panel9.png",
    btn: "assets/ui/button.png",
    btn_down: "assets/ui/button_pressed.png",
    icon_stats: "assets/ui/icon_stats.png",
    icon_close: "assets/ui/icon_close.png",
    icon_wood: "assets/ui/icon_wood.png",
    icon_gold: "assets/ui/icon_gold.png",
};

export const RESOURCE_ICONS = [
    ["wood", "icon_wood"],
    ["gold", "icon_gold"],
];
