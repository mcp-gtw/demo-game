const CLOUD_KEYS = ["cloud1", "cloud2", "cloud3"];

function between(min, max) {
    return min + Math.random() * (max - min);
}

// drifting clouds scattered at random over a bounds rectangle. On leaving the right edge a cloud
// wraps to the left with a fresh random height, size and speed, so they never line up or repeat.
export class Clouds {
    constructor(scene, { layer, bounds, count, scale = { min: 0.5, max: 1.2 }, speed = { min: 12, max: 30 } }) {
        this.bounds = bounds;
        this.scaleRange = scale;
        this.speedRange = speed;
        this.clouds = [];

        for (let i = 0; i < count; i += 1) {
            const cloud = scene.add.image(0, 0, CLOUD_KEYS[0]).setOrigin(0.5);
            layer.add(cloud);
            this.clouds.push(cloud);
            this.#reset(cloud, true);
        }
    }

    #reset(cloud, spread) {
        const { minX, maxX, minY, maxY } = this.bounds;
        cloud.setTexture(CLOUD_KEYS[Math.floor(Math.random() * CLOUD_KEYS.length)]);
        cloud.setScale(between(this.scaleRange.min, this.scaleRange.max)).setAlpha(between(0.65, 0.9));
        cloud.speed = between(this.speedRange.min, this.speedRange.max);
        cloud.y = between(minY, maxY);
        cloud.x = spread ? between(minX, maxX) : minX - cloud.displayWidth;
    }

    update(delta) {
        const seconds = delta / 1000;

        for (const cloud of this.clouds) {
            cloud.x += cloud.speed * seconds;

            if (cloud.x - cloud.displayWidth / 2 > this.bounds.maxX) {
                this.#reset(cloud, false);
            }
        }
    }
}
