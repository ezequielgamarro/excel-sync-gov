/**
 * T67/T68 — configuración de Playwright E2E y accesibilidad (CA-01.5,
 * CA-02.1/02.2/02.7, CA-03.x, CA-04.x, CA-05.x).
 *
 * Arranca la SPA en `http://localhost:5173` si no hay un `E2E_BASE_URL`
 * (despliegue/preview). Los tests que requieren backend real usan `E2E_API_URL`
 * y se auto-omiten si no está definida.
 */

import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.E2E_BASE_URL ?? "http://localhost:5173";

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: 1,
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL,
    trace: "on-first-retry",
    screenshot: "only-on-failure",
    video: "off",
  },
  projects: [
    {
      name: "chromium-1920",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1920, height: 1080 } },
    },
    {
      name: "chromium-4k",
      testMatch: /responsive\.spec\.ts/,
      use: { ...devices["Desktop Chrome"], viewport: { width: 3840, height: 2160 } },
    },
  ],
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command: "npm run dev -- --port 5173",
        url: "http://localhost:5173",
        reuseExistingServer: true,
        timeout: 120_000,
      },
});
