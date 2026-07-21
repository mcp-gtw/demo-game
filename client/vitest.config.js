import { defineConfig } from "vitest/config";

export default defineConfig({
    test: {
        environment: "jsdom",
        include: ["tests/**/*.test.js"],
        coverage: {
            provider: "v8",
            include: ["src/helpers/**/*.js", "src/net/**/*.js"],
            // Phaser glue (needs a live scene) is verified by the Playwright pass, not unit-tested
            exclude: ["src/helpers/animations.js"],
            thresholds: { lines: 100, functions: 100, branches: 100, statements: 100 },
        },
    },
});
