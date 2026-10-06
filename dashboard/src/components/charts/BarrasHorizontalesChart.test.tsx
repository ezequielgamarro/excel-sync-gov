/**
 * BarrasHorizontalesChart — barras horizontales reales (`layout="vertical"`).
 *
 * Eje Y de categorías de 160 px con `interval={0}`, altura dinámica y estados
 * `loading`/`error`/`SIN DATOS`.
 */

import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { BarrasHorizontalesChart } from "./BarrasHorizontalesChart";

const DATA = [
  { name: "Unidad Regional Norte", value: 4 },
  { name: "Unidad Regional Sur", value: 2 },
];

describe("BarrasHorizontalesChart", () => {
  it("renderiza las barras horizontales con la serie real", () => {
    render(
      <BarrasHorizontalesChart
        title="Vehículos Secuestrados por Regional"
        data={DATA}
        testId="barras-test"
      />,
    );
    expect(screen.getByTestId("barras-test")).toBeInTheDocument();
    expect(screen.getByText("Vehículos Secuestrados por Regional")).toBeInTheDocument();
  });

  it("sin datos muestra estado vacío (no demo)", () => {
    render(<BarrasHorizontalesChart title="Armas Secuestradas por Regional" />);
    expect(screen.getByRole("status")).toHaveTextContent("SIN DATOS");
  });

  it("muestra carga y error", () => {
    const { rerender } = render(<BarrasHorizontalesChart title="Armas" loading />);
    expect(screen.getByRole("status", { name: /Cargando/ })).toBeInTheDocument();

    rerender(<BarrasHorizontalesChart title="Armas" error="sin sesión" />);
    expect(screen.getByRole("alert")).toHaveTextContent("sin sesión");
  });

  it("usa layout vertical con eje Y ancho e interval={0}", () => {
    const source = readFileSync(
      join(dirname(fileURLToPath(import.meta.url)), "BarrasHorizontalesChart.tsx"),
      "utf8",
    );
    expect(source).toContain('layout="vertical"');
    expect(source).toContain("width={160}");
    expect(source).toContain("interval={0}");
  });
});
