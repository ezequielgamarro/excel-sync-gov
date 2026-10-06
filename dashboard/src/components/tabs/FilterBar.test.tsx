/**
 * FilterBar — filtros globales: SIN selector de Turno y Unidad Regional
 * DINÁMICA (nombres oficiales del backend) con fallback estático.
 */

import { useEffect } from "react";
import { describe, expect, it } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { FilterBar } from "./FilterBar";
import { FiltersProvider, useFilters } from "../../state/FiltersContext";

function Harness({ unidades }: { unidades: string[] }): JSX.Element {
  const { setUnidadesDisponibles } = useFilters();
  useEffect(() => {
    setUnidadesDisponibles(unidades);
  }, [unidades, setUnidadesDisponibles]);
  return <FilterBar />;
}

function renderBar(unidades: string[]): void {
  render(
    <FiltersProvider>
      <Harness unidades={unidades} />
    </FiltersProvider>,
  );
}

describe("FilterBar — sin Turno y Unidad Regional dinámica", () => {
  it("no renderiza ningún selector de Turno", () => {
    renderBar(["Unidad Regional Norte"]);
    expect(screen.queryByLabelText(/turno/i)).toBeNull();
    expect(document.getElementById("filter-turno")).toBeNull();
  });

  it("puebla Unidad Regional con los nombres reales del backend + «Todas»", () => {
    renderBar(["Unidad Regional Norte", "Unidad Regional Sur"]);
    const select = document.getElementById("filter-unidad") as HTMLSelectElement;
    const options = within(select)
      .getAllByRole("option")
      .map((option) => (option as HTMLOptionElement).value);
    expect(options).toEqual(["TODAS", "Unidad Regional Norte", "Unidad Regional Sur"]);
  });

  it("usa el fallback estático sólo si la lista dinámica viene vacía", () => {
    renderBar([]);
    const select = document.getElementById("filter-unidad") as HTMLSelectElement;
    const options = within(select)
      .getAllByRole("option")
      .map((option) => (option as HTMLOptionElement).value);
    expect(options).toEqual(["TODAS", "capital", "sur", "este", "oeste", "norte"]);
  });
});
