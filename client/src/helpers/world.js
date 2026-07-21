// flatten a world snapshot into a lookup of entity id to entity.

export function indexWorld(world) {
    const byId = new Map();
    const groups = [
        world.players,
        world.enemies,
        world.projectiles,
        world.food,
        world.trees,
        world.pickups,
        world.coins,
    ];

    for (const group of groups) {
        for (const entity of group) {
            byId.set(entity.id, entity);
        }
    }

    return byId;
}
