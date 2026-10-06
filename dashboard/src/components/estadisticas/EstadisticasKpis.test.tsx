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
  total_consultas: 1234,
  aprehendidos: 7,
  vehiculos_secuestrados: 12,
  armas_secuestradas: 3,
};

const KPIS: EstadisticasKpisData = {
  total_consultas: 99,
  aprehendidos: 5,
  personas: 4,
  vehiculos: 8,
  armas: 2,
  positivos: 6,
  negativos: 3,
};

function kpiCard(testKey: string): HTMLElement {
  const card = document.querySelector<HTMLElement>(`[data-kpi="${testKey}"]`);
  if (!card) throw new Error(`No se encontró la tarjeta ${testKey}`);
  return card;
}

describe("EstadisticasKpis", () => {
  it("renderiza los TOTALES reales en las 4 tarjetas", () => {
    render(<EstadisticasKpis totales={TOTALES} />);

    expect(kpiCard("total-consultas")).toHaveTextContent("1.234");
    expect(kpiCard("aprehendidos")).toHaveTextContent("7");
    expect(kpiCard("vehiculos-secuestrados")).toHaveTextContent("12");
    expect(kpiCard("armas-secuestradas")).toHaveTextContent("3");
  });

  it("cae a `kpis` cuando `totales` no trae una clave", () => {
    render(
      <EstadisticasKpis totales={{ total_consultas: 50 } as EstadisticasTotales} kpis={KPIS} />,
    );

    expect(kpiCard("total-consultas")).toHaveTextContent("50");
    expect(kpiCard("aprehendidos")).toHaveTextContent("5");
    expect(kpiCard("vehiculos-secuestrados")).toHaveTextContent("8");
    expect(kpiCard("armas-secuestradas")).toHaveTextContent("2");
  });

  it("usa el componente base oscuro, sin relleno plano rojo/verde", () => {
    render(<EstadisticasKpis totales={TOTALES} />);

    for (const testKey of [
      "total-consultas",
      "aprehendidos",
      "vehiculos-secuestrados",
      "armas-secuestradas",
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

    const indicator = kpiCard("total-consultas").querySelector(
      "span[aria-hidden][style]",
    ) as HTMLElement;

    expect(indicator.style.backgroundColor).toBe("var(--accent)");
  });

  it("sin totales ni kpis → 0 (nunca demo)", () => {
    render(<EstadisticasKpis />);
    expect(kpiCard("total-consultas")).toHaveTextContent("0");
    expect(kpiCard("aprehendidos")).toHaveTextContent("0");
    expect(kpiCard("vehiculos-secuestrados")).toHaveTextContent("0");
    expect(kpiCard("armas-secuestradas")).toHaveTextContent("0");
  });
});
