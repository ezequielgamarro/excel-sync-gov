/**
 * EvolucionDiariaChart — evolución diaria de incidentes por fecha.
 *
 * `<XAxis dataKey="fecha" />` + una serie `<Bar dataKey="total" />`. Estados
 * `loading`/`error`/`SIN DATOS`.
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { EvolucionDiariaChart } from "./EvolucionDiariaChart";

const DATA = [
  { fecha: "01/10", total: 6 },
  { fecha: "02/10", total: 11 },
];

describe("EvolucionDiariaChart", () => {
  it("renderiza el gráfico con los días reales", () => {
    render(<EvolucionDiariaChart data={DATA} />);
    expect(screen.getByTestId("chart-evolucion-diaria")).toBeInTheDocument();
    expect(screen.getByText("Evolución Diaria de Incidentes")).toBeInTheDocument();
  });

  it("sin datos muestra estado vacío (no demo)", () => {
    render(<EvolucionDiariaChart />);
    expect(screen.getByRole("status")).toHaveTextContent("SIN DATOS");
    expect(screen.queryByTestId("chart-evolucion-diaria")).not.toBeInTheDocument();
  });

  it("muestra carga y error", () => {
    const { rerender } = render(<EvolucionDiariaChart loading />);
    expect(screen.getByRole("status", { name: /Cargando/ })).toBeInTheDocument();

    rerender(<EvolucionDiariaChart error="sin sesión" />);
    expect(screen.getByRole("alert")).toHaveTextContent("sin sesión");
  });

  it("usa la fecha en XAxis y `total` como serie", () => {
    const source = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), "EvolucionDiariaChart.tsx"),
      "utf8",
    );
    expect(source).toContain('dataKey="fecha"');
    expect(source).toContain('dataKey="total"');
  });
});
