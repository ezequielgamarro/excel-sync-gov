import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

// =============================================================================
// Vite + React 18 + PWA (T47).
//
// - `build.rollupOptions.output` usa hashes en los assets (inmutables 1 año en
//   el edge, RNF-10.e / T73). El app shell se cachea en el Service Worker; las
//   respuestas de API y el WSS NUNCA se cachean (AM-10).
// - El cliente lee configuración no secreta por `import.meta.env.VITE_*`
//   (origen público de la API). No hay secretos en el bundle
//   (§2.2.5, RNF-13.b).
// =============================================================================
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: false,
  },
  build: {
    target: "es2022",
    sourcemap: false,
    chunkSizeWarningLimit: 900,
    rollupOptions: {
      output: {
        entryFileNames: "assets/[name]-[hash].js",
        chunkFileNames: "assets/[name]-[hash].js",
        assetFileNames: "assets/[name]-[hash][extname]",
      },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
  },
});
