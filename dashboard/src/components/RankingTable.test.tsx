/**
 * T66 — ranking/estados (RF-04.d/e/f/h): 4 columnas, hasta 5 filas sin relleno,
 * orden desc con desempate alfabético, variación con glifo+signo y estado vacío
 * `SIN DATOS` con motivo. CA-04.3, CA-04.4, CA-04.6.
 */

import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { RankingTable } from "./RankingTable";
import type { RankingItem } from "../types";

function dep(
  index: number,
  intervenciones: number,
  comisaria: string,
  variacionAbs = 0,
): RankingItem {
  return {
    puesto: index,
    dependencia_id: `d-${index}`,
    comisaria,
    intervenciones,
    variacion_abs: variacionAbs,
    variacion_pct: 1,
    puesto_previo: index,
  };
}

describe("RankingTable (RF-04, T66)", () => {
  it("limita a 5 filas y ordena por intervenciones desc (desempate alfabético)", () => {
    const items = [
      dep(1, 50, "Comisaría 3"),
      dep(2, 50, "Comisaría 1"),
      dep(3, 90, "Comisaría 9"),
      dep(4, 10, "Comisaría 4"),
      dep(5, 5, "Comisaría 5"),
      dep(6, 1, "Comisaría 6"),
      dep(7, 0, "Comisaría 7"),
    ].sort((a, b) =>
      b.intervenciones !== a.intervenciones
        ? b.intervenciones - a.intervenciones
        : a.comisaria.localeCompare(b.comisaria, "es"),
    );

    render(
      <RankingTable dependencias={items.slice(0, 5).map((d, i) => ({ ...d, puesto: i + 1 }))} />,
    );
    const table = screen.getByRole("table");
    const headers = within(table)
      .getAllByRole("columnheader")
      .map((h) => h.textContent);
    expect(headers).toEqual(["Posición", "Comisaría", "Intervenciones", "Variación"]);
    // 1 encabezado + 5 filas.
    expect(within(table).getAllByRole("row")).toHaveLength(6);
    expect(screen.getByText("Comisaría 9")).toBeInTheDocument();
    expect(screen.queryByText("Comisaría 6")).not.toBeInTheDocument();
  });

  it("formatea la variación con glifo + signo + coma decimal", () => {
    render(
      <RankingTable
        dependencias={[dep(1, 94, "Comisaría 12", 12), dep(2, 88, "Comisaría 7", -5)]}
      />,
    );
    expect(screen.getByText("+12 (+1,0 %)")).toBeInTheDocument();
    expect(screen.getByText("−5 (+1,0 %)")).toBeInTheDocument();
  });

  it("anuncia el cambio de puesto en el aria-label de la fila (RF-04.g)", () => {
    const item = dep(1, 94, "Comisaría 12", 12);
    item.puesto_previo = 2; // subió de 2 → 1
    render(<RankingTable dependencias={[item]} />);
    const row = screen.getByRole("row", { name: /Comisaría 12/ });
    expect(row.getAttribute("aria-label")).toContain("subió 1 puesto");
  });

  it("muestra SIN DATOS con motivo cuando no hay dependencias", () => {
    render(<RankingTable dependencias={[]} />);
    expect(screen.getByText("SIN DATOS")).toBeInTheDocument();
    expect(screen.getByText("sin datos en origen / sin datos en caché")).toBeInTheDocument();
  });
});
