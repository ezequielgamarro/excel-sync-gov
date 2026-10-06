/**
 * T67 — resolución y retícula responsiva (CA-05.1, CA-05.2, RF-05.c/d, RNF-10.b).
 *
 * - Sin scroll a 1920×1080 ni a 3840×2160.
 * - El contenido es visible y usable desde móvil (~375 px) hasta 4K.
 * - Por debajo de `lg` (1024 px) el sidebar funciona como drawer off-canvas.
 * - Sin aviso de "resolución no soportada" en ningún ancho.
 */

import { expect, test } from "@playwright/test";
import { installFakeWebSocket, mockDashboard } from "./fixtures";

async function documentOverflow(
  page: import("@playwright/test").Page,
): Promise<{ horizontal: number; vertical: number }> {
  return page.evaluate(() => ({
    horizontal: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    vertical: document.documentElement.scrollHeight - document.documentElement.clientHeight,
  }));
}

test("sin scroll a 1920×1080", async ({ page }) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  await installFakeWebSocket(page);
  await mockDashboard(page);
  await page.goto("/");
  await expect(page.locator("[data-kpi]")).toHaveCount(4);
  await expect(page.locator("#unsupported-resolution")).toHaveCount(0);
  const overflow = await documentOverflow(page);
  expect(overflow.horizontal).toBeLessThanOrEqual(1);
  expect(overflow.vertical).toBeLessThanOrEqual(1);
});

test("sin scroll a 3840×2160", async ({ page }) => {
  await page.setViewportSize({ width: 3840, height: 2160 });
  await installFakeWebSocket(page);
  await mockDashboard(page);
  await page.goto("/");
  await expect(page.locator("[data-kpi]")).toHaveCount(4);
  await expect(page.locator("#unsupported-resolution")).toHaveCount(0);
  const overflow = await documentOverflow(page);
  expect(overflow.horizontal).toBeLessThanOrEqual(1);
  expect(overflow.vertical).toBeLessThanOrEqual(1);
});

test("usable a 1024×768 (tablet): sidebar fijo y contenido visible", async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 768 });
  await installFakeWebSocket(page);
  await mockDashboard(page);
  await page.goto("/");

  await expect(page.locator("[data-kpi]")).toHaveCount(4);
  await expect(page.locator("#unsupported-resolution")).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: /informe operativo comparativo/i }),
  ).toBeVisible();
  // A partir de `lg` el sidebar es una columna fija y visible.
  await expect(page.getByRole("navigation", { name: "Secciones del panel" })).toBeVisible();
  const overflow = await documentOverflow(page);
  expect(overflow.horizontal).toBeLessThanOrEqual(1);
  expect(overflow.vertical).toBeLessThanOrEqual(1);
});

test("usable a 768×1024 (tablet retrato): sidebar como drawer", async ({ page }) => {
  await page.setViewportSize({ width: 768, height: 1024 });
  await installFakeWebSocket(page);
  await mockDashboard(page);
  await page.goto("/");

  await expect(page.locator("[data-kpi]")).toHaveCount(4);
  await expect(page.locator("#unsupported-resolution")).toHaveCount(0);

  const menuButton = page.getByRole("button", { name: "Abrir menú de navegación" });
  await expect(menuButton).toBeVisible();
  // Cerrado por defecto: off-canvas y fuera del árbol de accesibilidad.
  await expect(page.locator("#admin-sidebar")).toHaveAttribute("aria-hidden", "true");

  await menuButton.click();
  await expect(page.locator("#admin-sidebar")).toHaveAttribute("aria-hidden", "false");
  await expect(page.getByTestId("sidebar-overlay")).toBeVisible();

  await page.keyboard.press("Escape");
  await expect(page.locator("#admin-sidebar")).toHaveAttribute("aria-hidden", "true");
});

test("la dona de \"Distribución\" se dibuja con tamaño no nulo en todos los anchos", async ({ page }) => {
  await installFakeWebSocket(page);
  await mockDashboard(page);
  await page.goto("/#/resumen");
  await expect(page.locator("[data-kpi]")).toHaveCount(4);

  for (const width of [375, 640, 768, 1024, 1280, 1440, 1920]) {
    await page.setViewportSize({ width, height: 900 });
    // Recharts mide con ResizeObserver; se da un frame para recalcular.
    await page.waitForTimeout(400);
    const size = await page.evaluate(() => {
      const wrap = document.querySelector<HTMLElement>('[data-testid="chart-donut"]');
      const svg = wrap?.querySelector("svg.recharts-surface") ?? null;
      const box = (el: Element | null): { w: number; h: number } =>
        el ? { w: el.getBoundingClientRect().width, h: el.getBoundingClientRect().height } : { w: 0, h: 0 };
      return { wrap: box(wrap), svg: box(svg) };
    });
    expect(size.wrap.w, `ancho del contenedor @${width}`).toBeGreaterThan(0);
    expect(size.wrap.h, `alto del contenedor @${width}`).toBeGreaterThan(0);
    expect(size.svg.w, `ancho del svg @${width}`).toBeGreaterThan(0);
    expect(size.svg.h, `alto del svg @${width}`).toBeGreaterThan(0);
  }
});

test("usable a 375×667 (móvil): una columna y sin overflow horizontal", async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 667 });
  await installFakeWebSocket(page);
  await mockDashboard(page);
  await page.goto("/");

  await expect(page.locator("[data-kpi]")).toHaveCount(4);
  await expect(page.locator("#unsupported-resolution")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Abrir menú de navegación" })).toBeVisible();

  const overflow = await documentOverflow(page);
  expect(overflow.horizontal).toBeLessThanOrEqual(1);
});
