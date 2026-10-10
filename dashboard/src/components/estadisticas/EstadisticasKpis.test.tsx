/**
 * EstadisticasKpis — estética táctica y TOTALES reales.
 *
 * Regresión de diseño: las tarjetas NO usan rellenos planos rojo/verde
 * (`backgroundColor` brillante); usan el componente base oscuro `kpi-card`
 * con un acento lateral sutil cyan. Los valores salen de `totales` con
 * respaldo en `kpis`.
 */

import { describe, expect, it } from "vitest";
import { render } from "@testing-library/react";
import { EstadisticasKpis } from "./EstadisticasKpis";
import type { EstadisticasKpis as EstadisticasKpisData, EstadisticasTotales } from "../../types";

const TOTALES: EstadisticasTotales = {
  total_intervenciones: 1234,
  total_positivos: 7,
  consultas_personas: 12,
  consultas_vehiculos: 3,
  consultas_armas: 1,
};

const KPIS: EstadisticasKpisData = {
  total_intervenciones: 99,
  total_positivos: 5,
  consultas_personas: 4,
  consultas_vehiculos: 8,
  consultas_armas: 2,
};

function kpiCard(testKey: string): HTMLElement {
  const card = document.querySelector<HTMLElement>(`[data-kpi="${testKey}"]`);
  if (!card) throw new Error(`No se encontró la tarjeta ${testKey}`);
  return card;
}

describe("EstadisticasKpis", () => {
  it("renderiza los TOTALES reales en las 4 tarjetas", () => {
    render(<EstadisticasKpis totales={TOTALES} />);

    expect(kpiCard("total-intervenciones")).toHaveTextContent("1.234");
    expect(kpiCard("total-positivos")).toHaveTextContent("7");
    expect(kpiCard("consultas-personas")).toHaveTextContent("12");
    expect(kpiCard("consultas-vehiculos")).toHaveTextContent("3");
  });

  it("cae a `kpis` cuando `totales` no trae una clave", () => {
    render(
      <EstadisticasKpis totales={{ total_intervenciones: 50 } as EstadisticasTotales} kpis={KPIS} />,
    );

    expect(kpiCard("total-intervenciones")).toHaveTextContent("50");
    expect(kpiCard("total-positivos")).toHaveTextContent("5");
    expect(kpiCard("consultas-personas")).toHaveTextContent("4");
    expect(kpiCard("consultas-vehiculos")).toHaveTextContent("8");
  });

  it("usa el componente base oscuro, sin relleno plano rojo/verde", () => {
    render(<EstadisticasKpis totales={TOTALES} />);

    for (const testKey of [
      "total-intervenciones",
      "total-positivos",
      "consultas-personas",
      "consultas-vehiculos",
    ]) {
      const card = kpiCard(testKey);
      expect(card.className).toContain("kpi-card");
      // Sin estilo inline de relleno brillante.
      expect(card.style.backgroundColor).toBe("");
      expect(card.getAttribute("style") ?? "").not.toMatch(/background-color/i);
    }
  });

  it("mantiene el acento lateral cyan sutil", () => {
    render(<EstadisticasKpis totales={TOTALES} />);

    const indicator = kpiCard("total-intervenciones").querySelector(
      "span[aria-hidden][style]",
    ) as HTMLElement;

    expect(indicator.style.backgroundColor).toBe("var(--accent)");
  });

  it("sin totales ni kpis → 0 (nunca demo)", () => {
    render(<EstadisticasKpis />);
    expect(kpiCard("total-intervenciones")).toHaveTextContent("0");
    expect(kpiCard("total-positivos")).toHaveTextContent("0");
    expect(kpiCard("consultas-personas")).toHaveTextContent("0");
    expect(kpiCard("consultas-vehiculos")).toHaveTextContent("0");
  });
});
