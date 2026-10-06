import js from "@eslint/js";
import globals from "globals";
import tseslint from "typescript-eslint";
import eslintConfigPrettier from "eslint-config-prettier";

// =============================================================================
// ESLint flat config (dashboard) — T5.
//
// - Lint de TypeScript/TSX con reglas recomendadas (typescript-eslint).
// - `eslint-config-prettier` desactiva reglas de estilo que entran en conflicto
//   con Prettier (la fuente de estilo es Prettier, no ESLint).
// - Se excluyen artefactos generados (dist, node_modules, build).
// =============================================================================
export default tseslint.config(
  {
    ignores: ["dist", "build", "node_modules", "coverage", "playwright-report", "test-results"],
  },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      globals: {
        ...globals.browser,
        ...globals.es2022,
      },
    },
  },
  {
    // E2E (Playwright) y su config: entorno Node (process, Buffer) + browser.
    files: ["e2e/**/*.ts", "playwright.config.ts"],
    languageOptions: {
      globals: {
        ...globals.node,
        ...globals.browser,
      },
    },
  },
  {
    // Service Worker (solo shell): globals de `ServiceWorkerGlobalScope`.
    files: ["public/sw.js"],
    languageOptions: {
      globals: {
        ...globals.serviceworker,
      },
    },
  },
  eslintConfigPrettier,
);
