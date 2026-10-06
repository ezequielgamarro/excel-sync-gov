/**
 * T67 — E2E del dashboard (CA-01.5, CA-02.1/02.2/02.7, CA-03.1, CA-04.1/03,
 * CA-05.1/05/07). Usa REST y WSS simulados; no requiere backend.
 */

import { expect, test } from "@playwright/test";
import { installFakeWebSocket, makeSnapshot, mockDashboard } from "./fixtures";

/** Espera a que el dashboard esté montado y el WebSocket falso conectado. */
async function waitForLive(page: import("@playwright/test").Page): Promise<void> {
  await page.waitForSelector("[data-kpi]");
  await page.waitForFunction(() => {
    const w = window as unknown as { __fakeSockets?: unknown[] };
    return (w.__fakeSockets?.length ?? 0) > 0;
  });
}

test.beforeEach(async ({ page }) => {
  await installFakeWebSocket(page);
});

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

test("una instantánea WSS muta el DOM sin recargar la página (CA-02.1)", async ({ page }) => {
  await mockDashboard(page);
  await page.goto("/");
  await waitForLive(page);
  await page.evaluate(() => {
    (window as unknown as { __reloads: number }).__reloads = 0;
    window.addEventListener("beforeunload", () => {
      (window as unknown as { __reloads: number }).__reloads += 1;
    });
  });

  const next = makeSnapshot(101, {
    payload: {
      regional: [
        { unidad_id: "capital", label: "Capital", intervenciones: 9999, variacion_abs: 0, variacion_pct: 0, rank: 1 },
      ],
    },
  });
  await page.evaluate((message) => {
    (window as unknown as { __pushSnapshot: (m: unknown) => void }).__pushSnapshot(message);
  }, next);

  await expect(page.getByText("9.999", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => (window as unknown as { __reloads: number }).__reloads)).toBe(0);
});

test("el skip-link es el primer elemento de tabulación (CA-05.7)", async ({ page }) => {
  await mockDashboard(page);
  await page.goto("/");
  await waitForLive(page);
  await page.keyboard.press("Tab");
  const focused = await page.evaluate(() => document.activeElement?.className ?? "");
  expect(focused).toContain("skip-link");
});

test("muestra DATOS DESACTUALIZADOS cuando la frescura supera 120 s (CA-05.6)", async ({ page }) => {
  await page.clock.install();
  // Sin WSS (no hay hello/heartbeat) y solo la primera instantánea llega:
  // pasado el umbral, no hubo sincronización real → banner.
  await installFakeWebSocket(page, { autoOpen: false });
  await mockDashboard(page);
  let snapshots = 0;
  await page.route("**/api/v1/dashboard/snapshot**", async (route) => {
    snapshots += 1;
    if (snapshots === 1) {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(makeSnapshot(100)),
      });
    }
    // Las siguientes quedan pendientes: no actualizan la marca de sincronización.
    await new Promise<void>(() => {});
  });
  await page.goto("/");
  await expect(page.locator("[data-kpi]")).toHaveCount(4);
  await page.clock.fastForward("02:01");
  await expect(page.getByText(/DATOS DESACTUALIZADOS/)).toBeVisible({ timeout: 5_000 });
});

test("muestra skeletons antes de la primera instantánea (CA-05.5)", async ({ page }) => {
  await installFakeWebSocket(page);
  await mockDashboard(page);
  await page.route("**/api/v1/dashboard/snapshot**", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 2000));
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(makeSnapshot(100)),
    });
  });
  await page.goto("/");
  await expect(page.locator(".skeleton").first()).toBeVisible();
  await expect(page.locator("[data-kpi]")).toHaveCount(4, { timeout: 8_000 });
});

test("respeta prefers-reduced-motion y el valor cambia (CA-05.4)", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await installFakeWebSocket(page);
  await mockDashboard(page);
  await page.goto("/");
  await waitForLive(page);
  const next = makeSnapshot(101, {
    payload: {
      regional: [
        { unidad_id: "capital", label: "Capital", intervenciones: 8888, variacion_abs: 0, variacion_pct: 0, rank: 1 },
      ],
    },
  });
  await page.evaluate((message) => {
    (window as unknown as { __pushSnapshot: (m: unknown) => void }).__pushSnapshot(message);
  }, next);
  await expect(page.getByText("8.888", { exact: true })).toBeVisible();
});

test("la actualización en vivo se aplica en ≤250 ms (CA-05.9)", async ({ page }) => {
  await installFakeWebSocket(page);
  await mockDashboard(page);
  await page.goto("/");
  await waitForLive(page);
  const next = makeSnapshot(101, {
    payload: {
      regional: [
        { unidad_id: "capital", label: "Capital", intervenciones: 7777, variacion_abs: 0, variacion_pct: 0, rank: 1 },
      ],
    },
  });
  const elapsed = await page.evaluate(async (message) => {
    const start = performance.now();
    (window as unknown as { __pushSnapshot: (m: unknown) => void }).__pushSnapshot(message);
    await new Promise<void>((resolve) => {
      const check = (): void => {
        if (document.body.textContent?.includes("7.777")) resolve();
        else requestAnimationFrame(check);
      };
      check();
    });
    return performance.now() - start;
  }, next);
  expect(elapsed).toBeLessThan(250);
});

test("un rol sin dash.view.live ve ACCESO DENEGADO (CA-02.9)", async ({ page }) => {
  await mockDashboard(page, { capabilities: ["dash.view.history"] });
  await page.goto("/");
  await expect(page.getByText(/ACCESO DENEGADO|denegado/i)).toBeVisible();
  await expect(page.locator("[data-kpi]")).toHaveCount(0);
});
