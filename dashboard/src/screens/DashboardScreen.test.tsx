/**
 * DashboardScreen — conexión de datos de Incidentes/Logística/Estadísticas.
 *
 * La fuente es `useIntervenciones` (Supabase `intervenciones_diarias`). Los
 * charts deben renderizar los arrays reales derivados; «SIN DATOS» sólo cuando
 * no hay datos.
 *
 * Los KPIs superiores se alimentan de `intervenciones.totales` (sin snapshot
 * semilla) y muestran el footer de comparación según el período elegido.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { AuthSession } from "../auth/session";
import { fireEvent, render, screen } from "@testing-library/react";
import type { UseIntervencionesResult } from "../hooks/useIntervenciones";
import type { UseDashboardResult } from "../hooks/useDashboard";

const mocks = vi.hoisted(() => ({
  intervenciones: {
    fase: "listo",
    datos: null,
    error: null,
    refetch: () => {},
  } as UseIntervencionesResult,
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
}));

vi.mock("../hooks/useIntervenciones", () => ({
  useIntervenciones: () => mocks.intervenciones,
}));
vi.mock("../hooks/useDashboard", () => ({ useDashboard: () => mocks.dashboard }));
// `HistorialRegistros` importa el cliente real; en tests no hay env de Supabase,
// así que se mockea para evitar `createClient("", "")` (supabaseUrl required).
vi.mock("../supabaseClient", () => ({
  supabase: {
    from: () => ({
      select: () => ({
        order: () => ({
          range: () => Promise.resolve({ data: [], count: 0, error: null }),
        }),
      }),
    }),
  },
}));

import { DashboardScreen } from "./DashboardScreen";
import { ComparisonProvider } from "../state/ComparisonContext";
import { FiltersProvider } from "../state/FiltersContext";

const SESION_ADMIN: AuthSession = {
  sub: "admin-test",
  accessToken: "token",
  refreshToken: null,
  csrfToken: null,
  expiresAt: Date.now() + 3_600_000,
  capabilities: ["dash.view.live"],
  roles: ["platform-admin"],
};

function renderScreen(hash: string): void {
  window.location.hash = hash;
  render(
    <ComparisonProvider>
      <FiltersProvider>
        <DashboardScreen session={SESION_ADMIN} onLogout={() => {}} />
      </FiltersProvider>
    </ComparisonProvider>,
  );
}

beforeEach(() => {
  mocks.intervenciones = { fase: "listo", datos: null, error: null, refetch: () => {} };
});

afterEach(() => {
  window.location.hash = "";
});

describe("DashboardScreen · fuente primaria estadísticas", () => {
  it("Incidentes: linea y barras usan las series reales de estadisticas", () => {
    mocks.intervenciones = {
      fase: "listo",
      datos: {
        estado: "exito",
        incidentes_por_dia: [
          { name: "2026-10-05", value: 3 },
          { name: "2026-10-06", value: 8 },
        ],
        incidentes_por_fecha: [
          { fecha: "05/10", total: 3 },
          { fecha: "06/10", total: 8 },
        ],
        incidentes_por_hora: [
          { name: "10:00", value: 3 },
          { name: "11:00", value: 8 },
        ],
        intervenciones_por_unidad: [{ name: "Unidad Regional Norte", value: 42 }],
      },
      error: null,
      refetch: () => {},
    };

    renderScreen("#/incidentes");

    // Flujo de Incidentes: flujo de consultas + evolución diaria.
    expect(screen.getByTestId("chart-realtime")).toBeInTheDocument();
    expect(screen.getByTestId("chart-evolucion-diaria")).toBeInTheDocument();
    // «Intervenciones por Unidad Regional» ya no está en Flujo de Incidentes.
    expect(screen.queryByTestId("chart-columns-unidad")).toBeNull();
    expect(screen.queryByText("SIN DATOS")).toBeNull();
  });

  it("Estadística Total CISOP: KPIs en gráficos y gráfico por Unidad Regional", () => {
    mocks.intervenciones = {
      fase: "listo",
      datos: {
        estado: "exito",
        totales: {
          total_intervenciones: 100,
          total_positivos: 30,
          consultas_personas: 40,
          consultas_vehiculos: 30,
          consultas_armas: 20,
          consultas_elementos: 10,
        },
        totales_previos: {
          total_intervenciones: 80,
          total_positivos: 20,
          consultas_personas: 30,
          consultas_vehiculos: 25,
          consultas_armas: 15,
          consultas_elementos: 10,
        },
        intervenciones_por_unidad: [{ name: "U.R. Norte", value: 42 }],
      },
      error: null,
      refetch: () => {},
    };

    renderScreen("#/comparativas");

    expect(screen.getByTestId("chart-kpi-comparacion")).toBeInTheDocument();
    expect(screen.getByTestId("chart-kpi-tipos")).toBeInTheDocument();
    expect(screen.getByTestId("chart-columns-unidad")).toBeInTheDocument();
  });

  it("Logística: barras horizontales reales de vehículos y armas (sin donut ni turnos)", () => {
    mocks.intervenciones = {
      fase: "listo",
      datos: {
        estado: "exito",
        vehiculosPorRegional: [{ name: "Unidad Regional Sur", value: 4 }],
        armasPorRegional: [{ name: "Unidad Regional Norte", value: 2 }],
        distribucion_incidentes: [{ name: "VEHICULO", value: 4 }],
        totales: {
          total_intervenciones: 9,
          total_positivos: 6,
          consultas_personas: 1,
          consultas_vehiculos: 4,
          consultas_armas: 2,
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
    expect(screen.getByText("Consultas de Vehículos").parentElement?.textContent).toContain("4");
    expect(screen.getByText("Consultas de Armas").parentElement?.textContent).toContain("2");
  });

  it("Estadísticas: panel maestro renderiza TODOS los gráficos del sistema", () => {
    mocks.intervenciones = {
      fase: "listo",
      datos: {
        estado: "exito",
        distribucion_incidentes: [{ name: "VEHICULO", value: 6 }],
        incidentes_por_dia: [{ name: "2026-10-06", value: 2 }],
        incidentes_por_hora: [{ name: "08:00", value: 2 }],
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
            positivos: 7,
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
    // Selector dinámico de Unidad Regional (nombres oficiales de Supabase).
    // Ahora está en la cabecera (Header). Usamos getAllByRole porque hay un solo
    // FilterBar en la cabecera; getAllByRole evita el error si hubiera duplicados.
    const unidadOptions = screen.getAllByRole("option", { name: "Unidad Regional Norte" });
    expect(unidadOptions.length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByLabelText(/turno/i)).toBeNull();
  });

  it("Resumen: Evolución Diaria usa la serie real incidentes_por_fecha", () => {
    mocks.intervenciones = {
      fase: "listo",
      datos: {
        estado: "exito",
        incidentes_por_fecha: [
          { fecha: "01/10", total: 6 },
          { fecha: "02/10", total: 11 },
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
    mocks.intervenciones = {
      fase: "listo",
      datos: {
        estado: "exito",
        totales: {
          total_intervenciones: 365,
          total_positivos: 10,
          consultas_personas: 4,
          consultas_vehiculos: 2,
          consultas_armas: 1,
        },
      },
      error: null,
      refetch: () => {},
    };

    renderScreen("#/resumen");

    const card = document.querySelector<HTMLElement>('[data-kpi="total_intervenciones"]');
    expect(card?.textContent).toContain("365");
    expect(document.body.textContent).not.toContain("184.732");
    expect(screen.getAllByText("— sin Ayer").length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("radio", { name: "Mes anterior" }));
    expect(screen.getAllByText("— sin Mes anterior").length).toBeGreaterThan(0);
    expect(screen.queryByText("— sin Ayer")).toBeNull();
  });

  it("Resumen: KPIs usan totales derivados de Supabase y variación real (sin 'N/A')", () => {
    mocks.intervenciones = {
      fase: "listo",
      datos: {
        estado: "exito",
        totales: {
          total_intervenciones: 2579,
          total_positivos: 180,
          consultas_personas: 420,
          consultas_vehiculos: 310,
          consultas_armas: 75,
          consultas_elementos: 12,
        },
        totales_previos: {
          total_intervenciones: 2000,
          total_positivos: 150,
          consultas_personas: 300,
          consultas_vehiculos: 200,
          consultas_armas: 50,
          consultas_elementos: 10,
        },
      },
      error: null,
      refetch: () => {},
    };

    renderScreen("#/resumen");

    const card = document.querySelector<HTMLElement>('[data-kpi="total_intervenciones"]');
    expect(card?.textContent).toContain("2.579");
    expect(card?.textContent).toContain("2.000");
    expect(
      document.querySelector<HTMLElement>('[data-kpi="consultas_armas"]')?.textContent,
    ).toContain("75");
    expect(
      document.querySelector<HTMLElement>('[data-kpi="consultas_elementos"]')?.textContent,
    ).toContain("12");
    expect(document.body.textContent).not.toContain("N/A");
    expect(document.body.textContent).not.toContain("— sin Ayer");
  });

  it("Resumen: Ranking Top 5 usa datos.rankingTop5 (no el snapshot semilla)", () => {
    mocks.intervenciones = {
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
            positivos: 15,
          },
          {
            name: "Comisaría Primera",
            intervenciones: 120,
            value: 120,
            variacion_abs: 0,
            variacion_pct: null,
            positivos: 0,
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
