import { defineConfig } from "vitest/config";
// Node test env has no DOM storage; i18n.ts reads localStorage (and
// navigator.language) at module load, so stub them before any import.
export default defineConfig({
    test: {
        setupFiles: ["src/test-setup.ts"],
    },
});
