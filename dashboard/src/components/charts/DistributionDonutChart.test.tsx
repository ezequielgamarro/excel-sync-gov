/**
 * DistributionDonutChart — contrato real + estados.
 *
 * - Con datos reales (`groups`) renderiza dona y leyenda; el contenedor de la
 *   dona tiene dimensiones no nulas (regresión de layout).
 * - Sin datos → estado vacío (nunca demo).
 * - `loading`/`error` muestran estados explícitos.
 */

import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { DistributionDonutChart } from "./DistributionDonutChart";
import type { ConsultaGroup } from "../../types";

const GROUPS: ConsultaGroup[] = [
  { key: "robos", label: "Robos", value: 40 },
  { key: "siniestros", label: "Siniestros", value: 10 },
];

describe("DistributionDonutChart — datos reales", () => {
  it("declara tamaño mínimo y desacople de altura en el contenedor de la dona", () => {
    render(<DistributionDonutChart title="Distribución de Incidentes" groups={GROUPS} />);
    const donut = screen.getByTestId("chart-donut");

    expect(donut.className).toContain("min-h-[150px]");
    expect(donut.className).toContain("min-w-0");
    expect(donut.className).toContain("w-full");
    expect(donut.className).toContain("flex-1");
    expect(donut.className).toContain("relative");
    expect(donut.className).toContain("overflow-hidden");
    expect(donut.className).toContain("lg:min-h-0");

    const sizingBox = donut.querySelector("div.absolute.inset-0");
    expect(sizingBox).not.toBeNull();
    expect(sizingBox?.querySelector(".recharts-responsive-container")).not.toBeNull();
  });

  it("usa layout lateral desde `lg` con leyenda de ancho acotado", () => {
    render(<DistributionDonutChart title="Distribución de Incidentes" groups={GROUPS} />);
    const donut = screen.getByTestId("chart-donut");
    const flex = donut.parentElement as HTMLElement;

    expect(flex.className).toContain("lg:flex-row");
    expect(flex.className).toContain("lg:items-stretch");
    expect(flex.className).not.toContain("sm:flex-row");

    const legend = screen.getByRole("list", { name: "Leyenda de distribución" });
    expect(legend.className).toContain("min-w-0");
    expect(legend.className).toContain("lg:w-56");
    expect(legend.className).not.toContain("sm:w-auto");
  });

  it("renderiza la leyenda con una fila por porción real y su porcentaje", () => {
    render(<DistributionDonutChart title="Distribución de Incidentes" groups={GROUPS} />);
    const legend = screen.getByRole("list", { name: "Leyenda de distribución" });
    expect(legend.querySelectorAll("li")).toHaveLength(2);
    expect(legend.textContent).toContain("Robos");
    expect(legend.textContent).toMatch(/%/);
  });

  it("sin datos muestra estado vacío (no demo)", () => {
    render(<DistributionDonutChart title="Distribución por Tipo" />);
    expect(screen.getByRole("status")).toHaveTextContent("SIN DATOS");
    expect(screen.queryByTestId("chart-donut")).not.toBeInTheDocument();
  });

  it("muestra carga y error", () => {
    const { rerender } = render(<DistributionDonutChart title="Distribución" loading />);
    expect(screen.getByRole("status", { name: /Cargando/ })).toBeInTheDocument();

    rerender(<DistributionDonutChart title="Distribución" error="timeout" />);
    expect(screen.getByRole("alert")).toHaveTextContent("timeout");
  });
});
