// health bar ratio, clamped to the [0, 1] range.

export function healthRatio(health, maxHealth) {
    if (!maxHealth) {
        return 0;
    }

    return Math.max(0, Math.min(1, health / maxHealth));
}
