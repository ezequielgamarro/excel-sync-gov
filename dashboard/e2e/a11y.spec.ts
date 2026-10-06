/**
 * T68 — Auditoría axe-core WCAG 2.2 AA (CA-02.8, CA-03.3, CA-05.3, CA-05.7).
 * Sin violaciones critical/serious en el dashboard.
 */

import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { installFakeWebSocket, mockDashboard } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await installFakeWebSocket(page);
  await mockDashboard(page);
});

test("el dashboard no tiene violaciones serias de accesibilidad", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("[data-kpi]")).toHaveCount(4);

  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
    .analyze();

  const blocking = results.violations.filter(
    (violation) => violation.impact === "critical" || violation.impact === "serious",
  );
  expect(
    blocking,
    blocking.map((v) => `${v.id}: ${v.help}`).join("\n"),
  ).toEqual([]);
});

test("las combinaciones de color cumplen contraste (CA-05.3)", async ({ page }) => {
  await page.goto("/");
  const results = await new AxeBuilder({ page }).withRules(["color-contrast"]).analyze();
  expect(results.violations).toEqual([]);
});
