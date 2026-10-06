/**
 * DashboardScreen — conexión de datos de Incidentes/Logística/Estadísticas.
 *
 * La fuente PRIMARIA es `useEstadisticas` (`GET /api/estadisticas`, Excel real
 * traducido). Con `useConsultas` vacío, los charts deben renderizar los arrays
 * reales; «SIN DATOS» sólo cuando ambos orígenes están vacíos.
 *
 * Los KPIs superiores se alimentan de `estadisticas.totales` (sin snapshot
 * semilla) y muestran el footer de comparación según el período elegido.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, within } from "@testing-library/react";
import type { UseEstadisticasResult } from "../hooks/useEstadisticas";
import type { UseConsultasResult } from "../hooks/useConsultas";
import type { UseDashboardResult } from "../hooks/useDashboard";

const mocks = vi.hoisted(() => ({
  estadisticas: {
    fase: "listo",
    datos: null,
    error: null,
    refetch: () => {},
  } as UseEstadisticasResult,
  consultas: {
    aggregation: null,
    loading: false,
    error: null,
  } as UseConsultasResult,
  dashboard: {
    state: {
      snapshot: null,
      phase: "live",
      attempt: 1,
      degraded: false,
      schemaError: null,
      invalidData: false,
    },
    stale: false,
    now: Date.now(),
    lastSyncAt: Date.now(),
  } as unknown as UseDashboardResult,
  /** Último rango pasado a `useEstadisticas` (verifica el refetch por período). */
  ultimoRango: undefined as string | undefined,
}));

vi.mock("../hooks/useEstadisticas", () => ({
  useEstadisticas: (rango?: string) => {
    mocks.ultimoRango = rango;
    return mocks.estadisticas;
  },
}));
vi.mock("../hooks/useConsultas", () => ({ useConsultas: () => mocks.consultas }));
vi.mock("../hooks/useDashboard", () => ({ useDashboard: () => mocks.dashboard }));

import { DashboardScreen } from "./DashboardScreen";
import { ComparisonProvider } from "../state/ComparisonContext";
import { FiltersProvider } from "../state/FiltersContext";

function renderScreen(hash: string): void {
  window.location.hash = hash;
  render(
    <ComparisonProvider>
      <FiltersProvider>
        <DashboardScreen session={null} onLogout={() => {}} />
      </FiltersProvider>
    </ComparisonProvider>,
  );
}

beforeEach(() => {
  mocks.estadisticas = { fase: "listo", datos: null, error: null, refetch: () => {} };
  mocks.consultas = { aggregation: null, loading: false, error: null };
});

afterEach(() => {
  window.location.hash = "";
});

describe("DashboardScreen · fuente primaria estadísticas", () => {
  it("Incidentes: linea y barras usan las series reales de estadisticas", () => {
    mocks.estadisticas = {
      fase: "listo",
      datos: {
        estado: "exito",
        incidentes_por_dia: [
          { name: "2026-10-05", value: 3 },
          { name: "2026-10-06", value: 8 },
        ],
        intervenciones_por_unidad: [{ name: "Unidad Regional Norte", value: 42 }],
      },
      error: null,
      refetch: () => {},
    };

    renderScreen("#/incidentes");

    expect(screen.getByTestId("chart-realtime")).toBeInTheDocument();
    expect(screen.getByTestId("chart-columns-unidad")).toBeInTheDocument();
    expect(screen.queryByText("SIN DATOS")).toBeNull();
  });

  it("Logística: barras horizontales reales de vehículos y armas (sin donut ni turnos)", () => {
    mocks.estadisticas = {
      fase: "listo",
      datos: {
        estado: "exito",
        vehiculosPorRegional: [{ name: "Unidad Regional Sur", value: 4 }],
        armasPorRegional: [{ name: "Unidad Regional Norte", value: 2 }],
        distribucion_incidentes: [{ name: "VEHICULO", value: 4 }],
        kpis: {
          total_consultas: 9,
          personas: 1,
          vehiculos: 4,
          armas: 2,
          positivos: 6,
          negativos: 3,
        },
      },
      error: null,
      refetch: () => {},
    };

    renderScreen("#/logistica");

    expect(screen.getByTestId("chart-logistica-vehiculos")).toBeInTheDocument();
    expect(screen.getByTestId("chart-logistica-armas")).toBeInTheDocument();
    expect(screen.queryByTestId("chart-donut")).toBeNull();
    expect(screen.queryByText("Incidentes por Turno Operativo")).toBeNull();
    expect(
      screen.getByText("Vehículos secuestrados").parentElement?.textContent,
    ).toContain("4");
    expect(
      screen.getByText("Armas secuestradas").parentElement?.textContent,
    ).toContain("2");
  });

  it("Estadísticas: panel maestro renderiza TODOS los gráficos del sistema", () => {
    mocks.estadisticas = {
      fase: "listo",
      datos: {
        estado: "exito",
        distribucion_incidentes: [{ name: "VEHICULO", value: 6 }],
        incidentes_por_dia: [{ name: "2026-10-06", value: 2 }],
        incidentes_por_fecha: [{ fecha: "06/10", total: 2 }],
        intervenciones_por_unidad: [{ name: "Unidad Regional Norte", value: 42 }],
        vehiculosPorRegional: [{ name: "Unidad Regional Sur", value: 4 }],
        armasPorRegional: [{ name: "Unidad Regional Norte", value: 2 }],
        rankingTop5: [
          {
            name: "Comisaría Novena 9°",
            intervenciones: 40,
            value: 40,
            variacion_abs: 5,
            variacion_pct: 12.5,
          },
        ],
        grafico_regionales: [{ name: "Unidad Regional Norte", value: 10 }],
        grafico_dependencias: [{ name: "Comisaría Primera", value: 5 }],
        alertas_resultados: [{ name: "POSITIVO", value: 3 }],
        regionales_disponibles: ["Unidad Regional Norte", "Unidad Regional Sur"],
      },
      error: null,
      refetch: () => {},
    };

    renderScreen("#/estadisticas");

    expect(screen.getByTestId("chart-evolucion-diaria")).toBeInTheDocument();
    expect(screen.getByTestId("chart-columns-unidad")).toBeInTheDocument();
    expect(screen.getByTestId("chart-donut")).toBeInTheDocument();
    expect(screen.getByTestId("chart-realtime")).toBeInTheDocument();
    expect(screen.getByTestId("chart-logistica-vehiculos")).toBeInTheDocument();
    expect(screen.getByTestId("chart-logistica-armas")).toBeInTheDocument();
    expect(screen.getByTestId("ranking-top5")).toBeInTheDocument();
    expect(screen.getByTestId("chart-estadisticas-regionales")).toBeInTheDocument();
    expect(screen.getByTestId("chart-estadisticas-dependencias")).toBeInTheDocument();
    expect(screen.getByTestId("chart-estadisticas-resultados")).toBeInTheDocument();
    // Selector dinámico de Unidad Regional (nombres oficiales del backend).
    expect(screen.getByRole("option", { name: "Unidad Regional Norte" })).toBeInTheDocument();
    expect(screen.queryByLabelText(/turno/i)).toBeNull();
  });

  it("Estadísticas: los botones de período cambian el rango del fetch", () => {
    mocks.estadisticas = {
      fase: "listo",
      datos: { estado: "exito" },
      error: null,
      refetch: () => {},
    };

    renderScreen("#/estadisticas");

    expect(mocks.ultimoRango).toBe("ayer");
    const panel = screen.getByRole("radiogroup", { name: "Período del panel de estadísticas" });
    fireEvent.click(within(panel).getByRole("radio", { name: "Mes anterior" }));
    expect(mocks.ultimoRango).toBe("mes");
    expect(within(panel).getByRole("radio", { name: "Mes anterior" })).toHaveAttribute(
      "aria-checked",
      "true",
    );
  });

  it("Resumen: Evolución Diaria deriva el total por fecha desde incidentes_turno_por_dia", () => {
    mocks.estadisticas = {
      fase: "listo",
      datos: {
        estado: "exito",
        incidentes_turno_por_dia: [
          { fecha: "01/10", mañana: 3, tarde: 1, noche: 2 },
          { fecha: "02/10", mañana: 2, tarde: 4, noche: 5 },
        ],
      },
      error: null,
      refetch: () => {},
    };

    renderScreen("#/resumen");

    expect(screen.getByTestId("chart-evolucion-diaria")).toBeInTheDocument();
    expect(screen.queryByTestId("chart-turnos-por-dia")).toBeNull();
    expect(screen.queryByText("Incidentes por Turno Operativo")).toBeNull();
  });

  it("Resumen: KPIs con TOTALES reales y footer dinámico según el período", () => {
    mocks.estadisticas = {
      fase: "listo",
      datos: {
        estado: "exito",
        totales: {
          total_consultas: 365,
          aprehendidos: 10,
          vehiculos_secuestrados: 4,
          armas_secuestradas: 2,
        },
      },
      error: null,
      refetch: () => {},
    };

    renderScreen("#/resumen");

    const card = document.querySelector<HTMLElement>('[data-kpi="total_consultas_sifcop"]');
    expect(card?.textContent).toContain("365");
    expect(document.body.textContent).not.toContain("184.732");
    expect(screen.getAllByText("— sin Ayer").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("radio", { name: "Mes anterior" }));
    expect(screen.getAllByText("— sin Mes anterior").length).toBeGreaterThan(0);
    expect(screen.queryByText("— sin Ayer")).toBeNull();
  });

  it("Resumen: Ranking Top 5 usa datos.rankingTop5 (no el snapshot semilla)", () => {
    mocks.estadisticas = {
      fase: "listo",
      datos: {
        estado: "exito",
        rankingTop5: [
          {
            name: "Comisaría Novena 9°",
            intervenciones: 8420,
            value: 8420,
            variacion_abs: 20,
            variacion_pct: 0.24,
          },
          {
            name: "Comisaría Primera",
            intervenciones: 120,
            value: 120,
            variacion_abs: 0,
            variacion_pct: null,
          },
        ],
      },
      error: null,
      refetch: () => {},
    };

    renderScreen("#/resumen");

    expect(screen.getByTestId("ranking-top5")).toBeInTheDocument();
    expect(screen.getByText("Comisaría Novena 9°")).toBeInTheDocument();
    expect(screen.getByText("8.420")).toBeInTheDocument();
  });

  it("SIN DATOS sólo si ambos orígenes vienen vacíos", () => {
    renderScreen("#/incidentes");

    expect(screen.getAllByText("SIN DATOS").length).toBeGreaterThan(0);
    expect(screen.queryByTestId("chart-realtime")).toBeNull();
    expect(screen.queryByTestId("chart-columns-unidad")).toBeNull();
  });
});
