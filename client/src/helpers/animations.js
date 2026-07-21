import { TREES, UNITS, unitBases } from "../constants.js";

function anim(scene, key, texture, frameRate, repeat) {
    if (scene.anims.exists(key)) {
        return;
    }

    scene.anims.create({
        key,
        frames: scene.anims.generateFrameNumbers(texture, {}),
        frameRate,
        repeat,
    });
}

export function buildAnimations(scene) {
    for (const [key, unit] of Object.entries(UNITS)) {
        for (const base of unitBases(key, unit)) {
            anim(scene, `${base}_idle`, `${base}_idle`, unit.idleRate, -1);
            anim(scene, `${base}_run`, `${base}_run`, unit.runRate, -1);

            if (unit.attackRate) {
                anim(scene, `${base}_attack`, `${base}_attack`, unit.attackRate, 0);
            }
        }
    }

    for (const tree of TREES) {
        anim(scene, `${tree.key}_sway`, tree.key, 6, -1);
    }

    anim(scene, "foam_drift", "foam", 10, -1);
}
