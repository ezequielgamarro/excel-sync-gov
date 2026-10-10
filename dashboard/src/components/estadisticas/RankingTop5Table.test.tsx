/**
 * RankingTop5Table — `.map()` directo sobre `data.rankingTop5`.
 *
 * Sin datos hardcodeados: sólo se muestran las filas reales
 * (`{ name, intervenciones, value, variacion_abs, variacion_pct, positivos }`),
 * posición 1..10, comisaría, intervenciones y el subtotal exacto de positivos
 * («Sin positivos» cuando es 0). Estados `loading`/`error`/`SIN DATOS`.
 */

import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { RankingTop5Table } from "./RankingTop5Table";

describe("RankingTop5Table", () => {
  it("mapea las filas reales con posición, comisaría, intervenciones y positivos", () => {
    render(
      <RankingTop5Table
        data={[
          {
            name: "Comisaría Novena 9°",
            intervenciones: 8420,
            value: 8420,
            variacion_abs: 120,
            variacion_pct: 1.45,
            positivos: 23,
          },
          {
            name: "Comisaría Primera",
            intervenciones: 120,
            value: 120,
            variacion_abs: 20,
            variacion_pct: null,
            positivos: 0,
          },
        ]}
      />,
    );

    expect(screen.getByText("Ranking Top 10")).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: "Positivos" })).toBeInTheDocument();
    expect(screen.getByText("Comisaría Novena 9°")).toBeInTheDocument();
    expect(screen.getByText("8.420")).toBeInTheDocument();
    expect(screen.getByText("23")).toBeInTheDocument();
    expect(screen.getByText("Comisaría Primera")).toBeInTheDocument();
    expect(screen.getByText("Sin positivos")).toBeInTheDocument();
    expect(screen.getByTestId("ranking-top5")).toBeInTheDocument();
  });

  it("sin datos → SIN DATOS (nunca demo)", () => {
    render(<RankingTop5Table data={[]} />);
    expect(screen.getByText("SIN DATOS")).toBeInTheDocument();
  });

  it("positivos: número exacto en verde al haber, «Sin positivos» neutro en cero", () => {
    render(
      <RankingTop5Table
        data={[
          {
            name: "Con positivos",
            intervenciones: 10,
            value: 10,
            variacion_abs: 5,
            variacion_pct: 12.5,
            positivos: 5,
          },
          {
            name: "Sin base",
            intervenciones: 4,
            value: 4,
            variacion_abs: 0,
            variacion_pct: null,
            positivos: 0,
          },
        ]}
      />,
    );

    const conPositivos = screen.getByText("5").closest("td");
    expect(conPositivos).toHaveAttribute("data-positivos", "pos");
    expect(conPositivos).toHaveClass("text-emerald-400");

    const sinPositivos = screen.getByText("Sin positivos").closest("td");
    expect(sinPositivos).toHaveAttribute("data-positivos", "none");
    expect(sinPositivos).toHaveClass("text-muted");
  });

  it("muestra carga y error", () => {
    const { rerender } = render(<RankingTop5Table loading />);
    expect(screen.getByRole("status", { name: /Cargando/ })).toBeInTheDocument();

    rerender(<RankingTop5Table error="sin sesión" />);
    expect(screen.getByRole("alert")).toHaveTextContent("sin sesión");
  });

  it("nunca muestra más de 10 filas", () => {
    const data = Array.from({ length: 14 }, (_, index) => ({
      name: `Dependencia ${index + 1}`,
      intervenciones: 100 - index,
      value: 100 - index,
      variacion_abs: 0,
      variacion_pct: null,
      positivos: 0,
    }));
    render(<RankingTop5Table data={data} />);
    expect(screen.queryByText("Dependencia 11")).toBeNull();
    expect(screen.getByText("Dependencia 10")).toBeInTheDocument();
  });
});
