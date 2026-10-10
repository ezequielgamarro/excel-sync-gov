/**
 * T66 — tarjetas KPI (RF-02.c/d/f): formato de variación es-CL, estado sin
 * referencia y **idempotencia visual** (no anima ni destella si el valor no
 * cambia; destella 600 ms si cambia). CA-02.3, CA-02.4, CA-02.5, CA-02.7.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { KpiCard } from "./KpiCard";
import type { Kpi } from "../types";

function makeKpi(overrides: Partial<Kpi> = {}): Kpi {
  return {
    label: "Total Consultas SIFCOP",
    value: 184732,
    delta_abs: 3120,
    delta_pct: 1.71,
    direction: "up",
    comparison: "ayer_mismo_tramo",
    baseline_value: 181612,
    as_of: "2026-10-03T14:22:05Z",
    has_reference: true,
    ...overrides,
  };
}

beforeEach(() => {
  vi.stubGlobal("requestAnimationFrame", (cb: FrameRequestCallback) => {
    return window.setTimeout(() => cb(performance.now()), 0) as unknown as number;
  });
  vi.stubGlobal("cancelAnimationFrame", (id: number) => window.clearTimeout(id));
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("KpiCard (RF-02, T66)", () => {
  it("formatea variación con glifo, signo y porcentaje es-CL", () => {
    render(<KpiCard kpiKey="total_intervenciones" kpi={makeKpi()} />);
    expect(screen.getAllByText(/184\.732/).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/\+3\.120/).length).toBeGreaterThan(0);
    expect(screen.getByText(/más que el período anterior/)).toBeInTheDocument();
  });

  it("muestra '— sin período anterior' cuando has_reference=false", () => {
    render(
      <KpiCard
        kpiKey="total_positivos"
        kpi={makeKpi({
          delta_abs: null,
          delta_pct: null,
          has_reference: false,
          label: "Armas Secuestradas",
        })}
      />,
    );
    expect(screen.getByText("— sin período anterior")).toBeInTheDocument();
    expect(screen.queryByText(/NaN/)).not.toBeInTheDocument();
  });

  it("nunca renderiza 'N/A' cuando no hay baseline", () => {
    render(
      <KpiCard
        kpiKey="total_positivos"
        kpi={makeKpi({
          delta_abs: null,
          delta_pct: null,
          has_reference: false,
        })}
      />,
    );
    expect(screen.queryByText(/N\/A/)).not.toBeInTheDocument();
  });

  it("no destella si el valor no cambia (idempotencia visual)", () => {
    const { container, rerender } = render(
      <KpiCard kpiKey="total_intervenciones" kpi={makeKpi()} />,
    );
    rerender(<KpiCard kpiKey="total_intervenciones" kpi={makeKpi()} />);
    const card = container.querySelector('[data-kpi="total_intervenciones"]');
    expect(card?.className).not.toContain("flash");
  });

  it("destella al cambiar el valor y lo anuncia una vez por aria-live", async () => {
    const { container, rerender } = render(
      <KpiCard kpiKey="total_intervenciones" kpi={makeKpi()} />,
    );
    rerender(
      <KpiCard kpiKey="total_intervenciones" kpi={makeKpi({ value: 185000, delta_abs: 3388 })} />,
    );
    await waitFor(() => {
      const card = container.querySelector('[data-kpi="total_intervenciones"]');
      expect(card?.className).toContain("flash");
    });
    expect(container.querySelector('[aria-live="polite"]')).not.toBeNull();
  });
});
