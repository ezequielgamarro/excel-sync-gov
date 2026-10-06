import { describe, expect, it } from "vitest";

import { aGrupos, aSerie, aTurnoDia } from "./estadisticas";

describe("aGrupos", () => {
  it("mapea series {name,value} a ConsultaGroup", () => {
    expect(aGrupos([{ name: "URC", value: 267 }])).toEqual([
      { key: "URC", label: "URC", value: 267 },
    ]);
  });

  it("null/undefined → arreglo vacío (sin datos inventados)", () => {
    expect(aGrupos(null)).toEqual([]);
    expect(aGrupos(undefined)).toEqual([]);
  });
});

describe("aSerie", () => {
  it("mapea series {name,value} a puntos {ts,value}", () => {
    expect(aSerie([{ name: "2026-10-05", value: 12 }])).toEqual([
      { ts: "2026-10-05", value: 12 },
    ]);
  });

  it("descarta valores no numéricos y conserva el orden", () => {
    const result = aSerie([
      { name: "2026-10-05", value: 12 },
      { name: "2026-10-06", value: Number.NaN },
      { name: "2026-10-07", value: 7 },
    ]);
    expect(result).toEqual([
      { ts: "2026-10-05", value: 12 },
      { ts: "2026-10-07", value: 7 },
    ]);
  });

  it("null/undefined/[] → arreglo vacío (sin datos inventados)", () => {
    expect(aSerie(null)).toEqual([]);
    expect(aSerie(undefined)).toEqual([]);
    expect(aSerie([])).toEqual([]);
  });
});

describe("aTurnoDia", () => {
  const ITEMS = [
    { fecha: "01/10", mañana: 3, tarde: 5, noche: 2 },
    { fecha: "02/10", mañana: 1, tarde: 4, noche: 6 },
  ];

  it("extrae la serie del turno conservando los días", () => {
    expect(aTurnoDia(ITEMS, "mañana")).toEqual([
      { key: "01/10", label: "01/10", value: 3 },
      { key: "02/10", label: "02/10", value: 1 },
    ]);
    expect(aTurnoDia(ITEMS, "noche")).toEqual([
      { key: "01/10", label: "01/10", value: 2 },
      { key: "02/10", label: "02/10", value: 6 },
    ]);
  });

  it("null/undefined → arreglo vacío (sin datos inventados)", () => {
    expect(aTurnoDia(null, "tarde")).toEqual([]);
    expect(aTurnoDia(undefined, "tarde")).toEqual([]);
  });
});
