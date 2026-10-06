/**
 * T66 — regional/estados (RF-03.b/e): 5 unidades en orden canónico y categoría
 * sin datos con barra 0 + texto "sin datos" (no se elimina del eje). CA-03.2.
 */

import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { RegionalChart } from "./RegionalChart";
import type { RegionalItem } from "../types";

const regional: RegionalItem[] = [
  {
    unidad_id: "capital",
    label: "Capital",
    intervenciones: 268,
    variacion_abs: 22,
    variacion_pct: 8.93,
    rank: 1,
  },
  {
    unidad_id: "sur",
    label: "Sur",
    intervenciones: 142,
    variacion_abs: -5,
    variacion_pct: -3.4,
    rank: 2,
  },
  {
    unidad_id: "este",
    label: "Este",
    intervenciones: 98,
    variacion_abs: 7,
    variacion_pct: 7.74,
    rank: 3,
  },
  {
    unidad_id: "oeste",
    label: "Oeste",
    intervenciones: 71,
    variacion_abs: -3,
    variacion_pct: -4.05,
    rank: 4,
  },
  {
    unidad_id: "norte",
    label: "Norte",
    intervenciones: 0,
    variacion_abs: 0,
    variacion_pct: 0,
    rank: 0,
  },
];

describe("RegionalChart (RF-03, T66)", () => {
  it("mantiene las 5 unidades en orden canónico con la ausente en 'sin datos'", () => {
    render(<RegionalChart regional={regional} />);
    const table = screen.getByRole("table");
    const labels = within(table)
      .getAllByRole("rowheader")
      .map((cell) => cell.textContent);
    expect(labels).toEqual(["Capital", "Sur", "Este", "Oeste", "Norte"]);
    expect(within(table).getByText("sin datos")).toBeInTheDocument();
  });

  it("etiqueta los valores de las unidades con datos", () => {
    render(<RegionalChart regional={regional} />);
    const table = screen.getByRole("table");
    expect(within(table).getByText("268")).toBeInTheDocument();
    expect(within(table).getByText("71")).toBeInTheDocument();
  });
});
