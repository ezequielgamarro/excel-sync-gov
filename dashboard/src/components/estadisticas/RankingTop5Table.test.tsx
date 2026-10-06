/**
 * RankingTop5Table — `.map()` directo sobre `data.rankingTop5`.
 *
 * Sin datos hardcodeados: sólo se muestran las filas reales
 * (`{ name, intervenciones, value, variacion_abs, variacion_pct }`), posición
 * 1..5, comisaría, intervenciones y variación («—» si no hay base anterior).
 * Estados `loading`/`error`/`SIN DATOS`.
 */

import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { RankingTop5Table } from "./RankingTop5Table";

describe("RankingTop5Table", () => {
  it("mapea las filas reales con posición, comisaría, intervenciones y variación", () => {
    render(
      <RankingTop5Table
        data={[
          {
            name: "Comisaría Novena 9°",
            intervenciones: 8420,
            value: 8420,
            variacion_abs: 120,
            variacion_pct: 1.45,
          },
          {
            name: "Comisaría Primera",
            intervenciones: 120,
            value: 120,
            variacion_abs: 20,
            variacion_pct: null,
          },
        ]}
      />,
    );

    expect(screen.getByText("Comisaría Novena 9°")).toBeInTheDocument();
    expect(screen.getByText("8.420")).toBeInTheDocument();
    expect(screen.getByText("Comisaría Primera")).toBeInTheDocument();
    // Sin base anterior → «—» (nunca un 0 inventado).
    expect(screen.getByText("—")).toBeInTheDocument();
    expect(screen.getByTestId("ranking-top5")).toBeInTheDocument();
  });

  it("sin datos → SIN DATOS (nunca demo)", () => {
    render(<RankingTop5Table data={[]} />);
    expect(screen.getByText("SIN DATOS")).toBeInTheDocument();
  });

  it("variación direccional: ▲ cyan al subir, ▼ rojo tenue al bajar y — neutro", () => {
    render(
      <RankingTop5Table
        data={[
          { name: "Sube", intervenciones: 10, value: 10, variacion_abs: 5, variacion_pct: 12.5 },
          { name: "Baja", intervenciones: 8, value: 8, variacion_abs: -3, variacion_pct: -27.3 },
          { name: "Sin base", intervenciones: 4, value: 4, variacion_abs: 9, variacion_pct: null },
          { name: "Plano", intervenciones: 2, value: 2, variacion_abs: 0, variacion_pct: 0 },
        ]}
      />,
    );

    const sube = screen.getByText(/▲/).closest("td");
    expect(sube).toHaveAttribute("data-variation", "pos");
    expect(sube?.textContent).toContain("+5");
    expect(sube).toHaveStyle({ color: "var(--accent-bright)" });

    const baja = screen.getByText(/▼/).closest("td");
    expect(baja).toHaveAttribute("data-variation", "neg");
    expect(baja?.textContent).toContain("−3");
    expect(baja).toHaveStyle({ color: "var(--neg)", opacity: "0.75" });

    // Sin base (pct null) y variación cero → «—» neutro (nunca 0 inventado).
    expect(screen.getAllByText("—").length).toBe(2);
  });

  it("muestra carga y error", () => {
    const { rerender } = render(<RankingTop5Table loading />);
    expect(screen.getByRole("status", { name: /Cargando/ })).toBeInTheDocument();

    rerender(<RankingTop5Table error="sin sesión" />);
    expect(screen.getByRole("alert")).toHaveTextContent("sin sesión");
  });

  it("nunca muestra más de 5 filas", () => {
    const data = Array.from({ length: 8 }, (_, index) => ({
      name: `Dependencia ${index + 1}`,
      intervenciones: 100 - index,
      value: 100 - index,
      variacion_abs: 0,
      variacion_pct: null,
    }));
    render(<RankingTop5Table data={data} />);
    expect(screen.queryByText("Dependencia 6")).toBeNull();
    expect(screen.getByText("Dependencia 5")).toBeInTheDocument();
  });
});
