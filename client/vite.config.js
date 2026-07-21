import { resolve } from "node:path";
import { defineConfig } from "vite";

// the built bundle lands in web/dist and is served under /static/dist, while the game art keeps
// living in web/assets under /static/assets, so runtime asset urls never change.
export default defineConfig({
    base: "/static/dist/",
    build: {
        outDir: resolve(import.meta.dirname, "../src/app/web/dist"),
        assetsDir: "assets",
        emptyOutDir: true,
    },
});
