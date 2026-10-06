import { describe, expect, it } from "vitest";
import { buildGroupBars, buildRegionalBars, buildTurnoBars } from "./barData";
import type { BarFilters } from "./barData";
import type { ConsultaGroup, RegionalItem, TurnoItem } from "../types";

const REGIONAL: RegionalItem[] = [
  {
    unidad_id: "capital",
    label: "Capital",
    intervenciones: 1000,
    variacion_abs: 20,
    variacion_pct: 2.04,
    rank: 1,
  },
  {
    unidad_id: "sur",
    label: "Sur",
    intervenciones: 500,
    variacion_abs: -10,
    variacion_pct: -1.96,
    rank: 2,
  },
  {
    unidad_id: "este",
    label: "Este",
    intervenciones: 0,
    variacion_abs: 0,
    variacion_pct: 0,
    rank: 0,
  },
];

const TURNOS: TurnoItem[] = [
  {
    turno_id: "MAÑANA",
    inicio_min: 360,
    fin_min: 840,
    label: "MAÑANA",
    intervenciones: 600,
    variacion_abs: 15,
    variacion_pct: 2.56,
    estado: "cerrada",
  },
  {
    turno_id: "TARDE",
    inicio_min: 840,
    fin_min: 1320,
    label: "TARDE",
    intervenciones: 400,
    variacion_abs: -5,
    variacion_pct: -1.23,
    estado: "en_curso",
  },
  {
    turno_id: "NOCHE",
    inicio_min: 1320,
    fin_min: 2160,
    label: "NOCHE",
    intervenciones: 200,
    variacion_abs: 0,
    variacion_pct: 0,
    estado: "pendiente",
  },
];

const BASE: BarFilters = { turno: "TODOS", unidad: "TODAS", rango: "24h" };

function byId(rows: ReturnType<typeof buildRegionalBars>, id: string) {
  const found = rows.find((row) => row.id === id);
  if (!found) throw new Error(`no bar ${id}`);
  return found;
}

describe("barData — datos reales, sin multiplicadores", () => {
  it("usa el valor real del snapshot tal cual (sin escalar por rango)", () => {
    const h24 = buildRegionalBars(REGIONAL, { ...BASE, rango: "24h" }, "ayer");
    const d30 = buildRegionalBars(REGIONAL, { ...BASE, rango: "30d" }, "ayer");
    expect(byId(h24, "capital").value).toBe(1000);
    expect(byId(d30, "capital").value).toBe(1000);
  });

  it("con período 'ayer' expone la variación real del snapshot", () => {
    const bars = buildRegionalBars(REGIONAL, BASE, "ayer");
    const capital = byId(bars, "capital");
    expect(capital.deltaAbs).toBe(20);
    expect(capital.deltaPct).toBe(2.04);
    expect(capital.baseline).toBe(980);
    expect(capital.direction).toBe("up");
  });

  it("sin histórico (períodos distintos de 'ayer') deja baseline/variación en null", () => {
    const bars = buildRegionalBars(REGIONAL, BASE, "anio");
    for (const bar of bars) {
      expect(bar.baseline).toBeNull();
      expect(bar.deltaAbs).toBeNull();
      expect(bar.deltaPct).toBeNull();
      expect(bar.direction).toBe("flat");
    }
  });

  it("marca highlight en la unidad/turno seleccionada sin ajustar al resto", () => {
    const selected = buildRegionalBars(REGIONAL, { ...BASE, unidad: "sur" }, "ayer");
    expect(byId(selected, "sur").highlight).toBe(true);
    expect(byId(selected, "capital").highlight).toBe(false);
    expect(byId(selected, "capital").value).toBe(1000);

    const turnos = buildTurnoBars(TURNOS, { ...BASE, turno: "MAÑANA" }, "ayer");
    const manana = turnos.find((bar) => bar.id === "MAÑANA");
    expect(manana?.highlight).toBe(true);
    expect(manana?.estado).toBe("cerrada");
  });

  it("buildGroupBars parte de la agrupación real y no inventa base", () => {
    const groups: ConsultaGroup[] = [
      { key: "a", label: "A", value: 12 },
      { key: "b", label: "B", value: 7 },
    ];
    const bars = buildGroupBars(groups);
    expect(bars.map((bar) => bar.value)).toEqual([12, 7]);
    expect(bars.every((bar) => bar.baseline === null && bar.deltaPct === null)).toBe(true);
  });

  it("buildGroupBars respeta el límite", () => {
    const groups: ConsultaGroup[] = Array.from({ length: 10 }, (_, i) => ({
      key: `k${i}`,
      label: `L${i}`,
      value: i,
    }));
    expect(buildGroupBars(groups, 3)).toHaveLength(3);
  });
});
