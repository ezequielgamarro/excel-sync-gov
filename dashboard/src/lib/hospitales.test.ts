/**
 * T — KPIs y distribución del módulo de hospitales.
 *
 * Verifica que se usan `kpis`/`chartData` del backend cuando están presentes
 * (sin sumar filas de totales) y el fallback por columnas cuando faltan.
 */

import { describe, expect, it } from "vitest";
import type { HospitalesEstadisticas } from "../types";
import { computeHospitalKpis, normalizeColumnName, numericValue } from "./hospitales";

function sample(): HospitalesEstadisticas {
  return {
    sheet: "Hoja1",
    columns: [
      "Localidad",
      "Homicidios",
      "Lesiones Culposas",
      "Heridos con arma de fuego",
      "Violencia familiar",
    ],
    rows: [
      {
        Localidad: "A",
        Homicidios: 1,
        "Lesiones Culposas": 2,
        "Heridos con arma de fuego": 3,
        "Violencia familiar": 4,
      },
      {
        Localidad: "B",
        Homicidios: 5,
        "Lesiones Culposas": 6,
        "Heridos con arma de fuego": 7,
        "Violencia familiar": 8,
      },
    ],
    total_rows: 2,
  };
}

function sampleWithApi(): HospitalesEstadisticas {
  return {
    ...sample(),
    kpis: {
      homicidios: 6,
      lesiones_culposas: 8,
      heridos_con_arma_de_fuego: 10,
      violencia_familiar: 12,
      femicidio: 0,
    },
    chartData: [
      { causa: "Violencia familiar", cantidad: 12 },
      { causa: "Heridos con arma de fuego", cantidad: 10 },
      { causa: "Lesiones Culposas", cantidad: 8 },
      { causa: "Homicidios", cantidad: 6 },
    ],
  };
}

describe("hospitales: normalización defensiva", () => {
  it("normaliza acentos, mayúsculas y espacios", () => {
    expect(normalizeColumnName("  Heridos con ARMA de Fuego ")).toBe("heridos con arma de fuego");
    expect(normalizeColumnName("Femicidio")).toBe("femicidio");
  });

  it("convierte celdas no numéricas a 0", () => {
    expect(numericValue(3)).toBe(3);
    expect(numericValue("4")).toBe(4);
    expect(numericValue(null)).toBe(0);
    expect(numericValue("x")).toBe(0);
    expect(numericValue(Number.NaN)).toBe(0);
  });
});

describe("computeHospitalKpis", () => {
  it("usa los kpis del backend (mapeando la clave normalizada)", () => {
    const byKey = Object.fromEntries(
      computeHospitalKpis(sampleWithApi()).map((kpi) => [kpi.key, kpi]),
    );
    expect(byKey.lesiones_culposas.value).toBe(8);
    expect(byKey.heridos_arma_fuego.value).toBe(10);
    expect(byKey.violencia_familiar.value).toBe(12);
    expect(byKey.homicidios.value).toBe(6);
    expect(byKey.femicidio.value).toBe(0);
  });

  it("cae al cálculo por columnas si el backend no envía kpis", () => {
    const byKey = Object.fromEntries(computeHospitalKpis(sample()).map((kpi) => [kpi.key, kpi]));
    expect(byKey.lesiones_culposas.value).toBe(8);
    expect(byKey.heridos_arma_fuego.value).toBe(10);
    expect(byKey.violencia_familiar.value).toBe(12);
    expect(byKey.homicidios.value).toBe(6);
    expect(byKey.femicidio.value).toBe(0);
    expect(byKey.femicidio.column).toBeNull();
  });

  it("no vuelve a sumar una fila de Totales presente en rows", () => {
    // El backend ya excluye "Totales"; si por error llegara, los kpis mandan.
    const withTotal = {
      ...sampleWithApi(),
      rows: [
        ...sampleWithApi().rows,
        { Localidad: "Totales", Homicidios: 6, "Lesiones Culposas": 8 },
      ],
    };
    const byKey = Object.fromEntries(computeHospitalKpis(withTotal).map((kpi) => [kpi.key, kpi]));
    expect(byKey.homicidios.value).toBe(6);
    expect(byKey.lesiones_culposas.value).toBe(8);
  });
});
