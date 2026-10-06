/**
 * T67 — WSS + reconexión + polling + cold start y estados de conexión
 * (CA-01.5, CA-02.1, CA-05.8, RNF-05).
 */

import { expect, test } from "@playwright/test";
import { installFakeWebSocket, makeSnapshot, mockDashboard } from "./fixtures";

test("el estado inicial es EN VIVO tras el cold start y el WSS (CA-05.8)", async ({ page }) => {
  await installFakeWebSocket(page);
  await mockDashboard(page);
  await page.goto("/");
  await expect(page.getByRole("status").filter({ hasText: "EN VIVO" })).toBeVisible();
  await expect(page.getByText(/Última actualización:/)).toBeVisible();
});

test("reconecta tras un cierre anómalo y vuelve a EN VIVO (RNF-05.a/c)", async ({ page }) => {
  await installFakeWebSocket(page);
  await mockDashboard(page);
  await page.goto("/");
  await expect(page.getByRole("status").filter({ hasText: "EN VIVO" })).toBeVisible();

  await page.evaluate(() => (window as unknown as { __dropSocket: (c?: number) => void }).__dropSocket(1006));
  await expect(page.getByRole("status").filter({ hasText: "EN VIVO" })).toBeVisible({ timeout: 10_000 });
  const sockets = await page.evaluate(
    () => (window as unknown as { __fakeSockets: unknown[] }).__fakeSockets.length,
  );
  expect(sockets).toBeGreaterThanOrEqual(2);
});

test("degrada a polling si el WSS no se establece en 60 s (CA-05.8, RNF-05.d)", async ({ page }) => {
  await page.clock.install();
  await installFakeWebSocket(page, { autoOpen: false });
  await mockDashboard(page);
  await page.goto("/");
  await page.clock.fastForward("01:01");
  await expect(page.getByRole("status").filter({ hasText: "DEGRADADO · POLLING" })).toBeVisible();
});

test("el cold start se re-solicita al reconectar (RNF-05.e)", async ({ page }) => {
  await installFakeWebSocket(page);
  let snapshotRequests = 0;
  await mockDashboard(page);
  // Registrada después ⇒ tiene prioridad (Playwright resuelve la última primero).
  await page.route("**/api/v1/dashboard/snapshot**", (route) => {
    snapshotRequests += 1;
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(makeSnapshot(100)) });
  });
  await page.goto("/");
  const before = snapshotRequests;
  await page.evaluate(() => (window as unknown as { __dropSocket: (c?: number) => void }).__dropSocket(1006));
  await expect
    .poll(() => snapshotRequests, { timeout: 10_000 })
    .toBeGreaterThan(before);
});
