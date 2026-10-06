import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { TurnosColumnsChart } from "./TurnosColumnsChart";
import type { ConsultaGroup } from "../../types";

const GROUPS: ConsultaGroup[] = [
  { key: "capital", label: "Capital", value: 120 },
  { key: "sur", label: "Sur", value: 80 },
];

describe("TurnosColumnsChart — datos reales y estados", () => {
  it("renderiza el gráfico con la agrupación real", () => {
    render(
      <TurnosColumnsChart title="Intervenciones" testId="chart-columns-unidad" groups={GROUPS} />,
    );
    expect(screen.getByTestId("chart-columns-unidad")).toBeInTheDocument();
  });

  it("sin datos muestra estado vacío (no demo)", () => {
    render(<TurnosColumnsChart title="Intervenciones" testId="chart-columns-unidad" />);
    expect(screen.getByRole("status")).toHaveTextContent("SIN DATOS");
    expect(screen.queryByTestId("chart-columns-unidad")).not.toBeInTheDocument();
  });

  it("muestra carga y error", () => {
    const { rerender } = render(
      <TurnosColumnsChart title="Intervenciones" testId="chart-columns-unidad" loading />,
    );
    expect(screen.getByRole("status", { name: /Cargando/ })).toBeInTheDocument();

    rerender(
      <TurnosColumnsChart title="Intervenciones" testId="chart-columns-unidad" error="sin sesión" />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("sin sesión");
  });
});
