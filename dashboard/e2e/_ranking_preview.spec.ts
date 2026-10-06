/** TEMPORAL — captura visual del panel Ranking Top 5 (se elimina al terminar). */

import { test } from "@playwright/test";
import { installFakeWebSocket, mockDashboard } from "./fixtures";

test.beforeEach(async ({ page }) => {
  await installFakeWebSocket(page);
});

test("captura ranking top 5", async ({ page }) => {
  await mockDashboard(page, {
    estadisticas: {
      estado: "exito",
      totales: {
        total_consultas: 365,
        aprehendidos: 10,
        vehiculos_secuestrados: 4,
        armas_secuestradas: 2,
      },
      kpis: {
        total_consultas: 365,
        personas: 10,
        vehiculos: 4,
        armas: 2,
        positivos: 30,
        negativos: 5,
      },
      incidentes_por_fecha: [
        { fecha: "01/10", total: 6 },
        { fecha: "02/10", total: 11 },
      ],
      vehiculosPorRegional: [{ name: "Unidad Regional Sur", value: 4 }],
      armasPorRegional: [{ name: "Unidad Regional Norte", value: 2 }],
      rankingTop5: [
        { name: "Comisaría 12", intervenciones: 94, value: 94, variacion_abs: 12, variacion_pct: 14.63 },
        { name: "Comisaría 7", intervenciones: 88, value: 88, variacion_abs: -4, variacion_pct: -4.35 },
        { name: "Comisaría 3", intervenciones: 81, value: 81, variacion_abs: 5, variacion_pct: 6.58 },
        { name: "Dependencia Norte", intervenciones: 74, value: 74, variacion_abs: 1, variacion_pct: 1.37 },
        { name: "Comisaría 21", intervenciones: 69, value: 69, variacion_abs: -6, variacion_pct: -8.0 },
      ],
      grafico_regionales: [{ name: "Capital", value: 268 }],
      grafico_dependencias: [{ name: "Comisaría 12", value: 94 }],
      alertas_resultados: [{ name: "POSITIVO", value: 30 }],
    },
  });

  await page.goto("/");
  await page.getByRole("heading", { name: "Ranking Top 5" }).waitFor();

  const panel = page.locator('[data-testid="ranking-top5"]');
  await panel.scrollIntoViewIfNeeded();
  await panel.screenshot({ path: "C:/Users/Kurek/AppData/Local/Temp/opencode/ranking-antes.png" });
});
