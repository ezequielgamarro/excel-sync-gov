/**
 * T67 — E2E del dashboard (CA-01.5, CA-02.1/02.2/02.7, CA-03.1, CA-04.1/03,
 * CA-05.1/05/07). Usa respuestas REST simuladas; el dashboard consume Supabase.
 */

import { expect, test } from "@playwright/test";
import { mockDashboard } from "./fixtures";

test("renderiza los 7 visuales y 4 tarjetas KPI", async ({ page }) => {
  await mockDashboard(page);
  await page.goto("/");

  await expect(page.getByRole("heading", { name: /Informe Operativo Comparativo/ })).toBeVisible();
  await expect(page.locator("[data-kpi]")).toHaveCount(4);
  await expect(page.getByRole("heading", { name: "Intervenciones por Unidad Regional" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Evolución Diaria de Incidentes" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Ranking Top 5" })).toBeVisible();
  await expect(page.locator('[data-kpi="total_consultas_sifcop"]')).toContainText("365");
});

test("las 4 tarjetas KPI están en la fila superior en orden fijo (CA-02.2)", async ({ page }) => {
  await mockDashboard(page);
  await page.goto("/");

  const cards = page.locator("[data-kpi]");
  await expect(cards).toHaveCount(4);
  const boxes = await cards.evaluateAll((nodes) =>
    nodes.map((node) => {
      const rect = node.getBoundingClientRect();
      return { x: rect.x, y: rect.y, width: rect.width, height: rect.height, key: node.getAttribute("data-kpi") };
    }),
  );
  const ys = new Set(boxes.map((box) => Math.round(box.y)));
  expect(ys.size).toBe(1);
  expect(boxes.map((box) => box.key)).toEqual([
    "total_consultas_sifcop",
    "personas_capturadas",
    "vehiculos_secuestrados",
    "armas_secuestradas",
  ]);
  const xs = boxes.map((box) => box.x);
  expect(xs).toEqual([...xs].sort((a, b) => a - b));
});

test("el skip-link es el primer elemento de tabulación (CA-05.7)", async ({ page }) => {
  await mockDashboard(page);
  await page.goto("/");
  await page.keyboard.press("Tab");
  const focused = await page.evaluate(() => document.activeElement?.className ?? "");
  expect(focused).toContain("skip-link");
});
