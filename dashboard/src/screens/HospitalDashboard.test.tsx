/**
 * T — módulo «Ingresos Hospitalarios»: render de KPIs desde el endpoint,
 * estados de error/reintento e integración en el sidebar (sección + aria).
 */

import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { HospitalDashboard } from "./HospitalDashboard";
import { AdminSidebar } from "../components/layout/AdminSidebar";
import type { HospitalesEstadisticas } from "../types";

const SAMPLE: HospitalesEstadisticas = {
  sheet: "Hoja1",
  columns: [
    "Localidad",
    "Homicidios",
    "Lesiones Culposas",
    "Heridos con arma de fuego",
    "Violencia familiar",
  ],
  rows: [
    {
      Localidad: "A",
      Homicidios: 1,
      "Lesiones Culposas": 2,
      "Heridos con arma de fuego": 3,
      "Violencia familiar": 4,
    },
    {
      Localidad: "B",
      Homicidios: 5,
      "Lesiones Culposas": 6,
      "Heridos con arma de fuego": 7,
      "Violencia familiar": 8,
    },
  ],
  total_rows: 2,
  kpis: {
    homicidios: 6,
    lesiones_culposas: 8,
    heridos_con_arma_de_fuego: 10,
    violencia_familiar: 12,
    femicidio: 0,
  },
  chartData: [
    { causa: "Violencia familiar", cantidad: 12 },
    { causa: "Heridos con arma de fuego", cantidad: 10 },
    { causa: "Lesiones Culposas", cantidad: 8 },
    { causa: "Homicidios", cantidad: 6 },
  ],
};

function okResponse(payload: unknown): Response {
  return {
    ok: true,
    status: 200,
    statusText: "OK",
    json: async () => payload,
  } as unknown as Response;
}

function errorResponse(): Response {
  return {
    ok: false,
    status: 404,
    statusText: "Not Found",
    json: async () => ({ error: { code: "NOT_FOUND", message: "No se encontró la planilla." } }),
  } as unknown as Response;
}

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("HospitalDashboard", () => {
  it("renderiza las tarjetas KPI sumando las columnas clave", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(okResponse(SAMPLE)));
    render(<HospitalDashboard />);

    expect(
      await screen.findByRole("group", { name: "Total Lesiones Culposas: 8" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("group", { name: "Total Heridos Arma de Fuego: 10" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("group", { name: "Total Violencia Familiar: 12" })).toBeInTheDocument();
    expect(screen.getByTestId("chart-hospital-causas")).toBeInTheDocument();
    expect(screen.queryByTestId("chart-hospital-localidades")).toBeNull();
    expect(screen.queryByText(/ingresos por localidad/i)).toBeNull();
  });

  it("muestra el banner de error y reintenta la carga", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(errorResponse())
      .mockResolvedValueOnce(okResponse(SAMPLE));
    vi.stubGlobal("fetch", fetchMock);
    render(<HospitalDashboard />);

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /reintentar/i }));

    expect(
      await screen.findByRole("group", { name: "Total Violencia Familiar: 12" }),
    ).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});

describe("AdminSidebar · Ingresos Hospitalarios", () => {
  it("incluye la sección y la marca activa", () => {
    render(<AdminSidebar activeTab="hospitales" onSelect={() => {}} />);
    const button = screen.getByRole("button", { name: /ingresos hospitalarios/i });
    expect(button).toHaveAttribute("aria-current", "page");
  });
});
