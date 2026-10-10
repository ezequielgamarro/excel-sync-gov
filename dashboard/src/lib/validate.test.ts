import { describe, expect, it } from "vitest";
import { normalizeRanking, validateSnapshotMessage } from "./validate";
import type { Kpi, RankingItem, SnapshotMessage } from "../types";
import { makeSnapshot } from "../test/fixtures";

type MutableSnapshot = {
  schema_version: string;
  payload: {
    kpis: Record<string, { value: number }>;
    regional: Array<Record<string, unknown>>;
    ranking: { dependencias: Array<Record<string, unknown>> };
  };
};

function mutable(): MutableSnapshot {
  return structuredClone(makeSnapshot()) as unknown as MutableSnapshot;
}

describe("validación defensiva (T51, §7.8 / RF-02.i / RF-03.h)", () => {
  it("acepta un sobre 1.0.0 válido", () => {
    const result = validateSnapshotMessage(makeSnapshot());
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.message.seq).toBe(10);
      expect(result.warnings).toHaveLength(0);
    }
  });

  it("rechaza una versión mayor no soportada", () => {
    const snap = mutable();
    snap.schema_version = "2.0.0";
    const result = validateSnapshotMessage(snap);
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toBe("schema_unsupported");
  });

  it("rechaza la instantánea completa ante un KPI negativo (fail-closed)", () => {
    const snap = mutable();
    snap.payload.kpis.armas_secuestradas.value = -1;
    const result = validateSnapshotMessage(snap);
    expect(result.ok).toBe(false);
    if (!result.ok) expect(result.reason).toBe("invalid");
  });

  it("rechaza NaN en un KPI", () => {
    const snap = mutable();
    snap.payload.kpis.total_consultas_sifcop.value = Number.NaN;
    expect(validateSnapshotMessage(snap).ok).toBe(false);
  });

  it("descarta una unidad desconocida y mantiene las 5 canónicas", () => {
    const snap = mutable();
    snap.payload.regional.push({
      unidad_id: "noreste",
      label: "Noreste",
      intervenciones: 10,
      variacion_abs: 1,
      variacion_pct: 1,
      rank: 6,
    });
    const result = validateSnapshotMessage(snap);
    expect(result.ok).toBe(true);
    if (result.ok) {
      const message = result.message as SnapshotMessage;
      expect(message.payload.regional).toHaveLength(5);
      expect(message.payload.regional.map((item) => item.unidad_id)).toEqual([
        "capital",
        "sur",
        "este",
        "oeste",
        "norte",
      ]);
      expect(result.warnings.some((w) => w.startsWith("rejected_unknown_unit"))).toBe(true);
    }
  });

  it("mantiene la categoría ausente con 0 intervenciones (RF-03.e)", () => {
    const snap = mutable();
    snap.payload.regional = snap.payload.regional.filter((item) => item.unidad_id !== "norte");
    const result = validateSnapshotMessage(snap);
    expect(result.ok).toBe(true);
    if (result.ok) {
      const norte = result.message.payload.regional.find((item) => item.unidad_id === "norte");
      expect(norte?.intervenciones).toBe(0);
      expect(norte?.rank).toBe(0);
    }
  });
});

describe("orden del ranking (RF-04.e)", () => {
  it("ordena desc por intervenciones y desempata alfabéticamente", () => {
    const items: RankingItem[] = [
      {
        puesto: 0,
        dependencia_id: "a",
        comisaria: "Comisaría 3",
        intervenciones: 50,
        variacion_abs: 0,
        variacion_pct: 0,
        puesto_previo: 0,
      },
      {
        puesto: 0,
        dependencia_id: "b",
        comisaria: "Comisaría 1",
        intervenciones: 50,
        variacion_abs: 0,
        variacion_pct: 0,
        puesto_previo: 0,
      },
      {
        puesto: 0,
        dependencia_id: "c",
        comisaria: "Comisaría 9",
        intervenciones: 90,
        variacion_abs: 0,
        variacion_pct: 0,
        puesto_previo: 0,
      },
    ];
    const ranked = normalizeRanking(items);
    expect(ranked.map((item) => item.comisaria)).toEqual([
      "Comisaría 9",
      "Comisaría 1",
      "Comisaría 3",
    ]);
    expect(ranked.map((item) => item.puesto)).toEqual([1, 2, 3]);
  });

  it("limita a 10 filas", () => {
    const items: RankingItem[] = Array.from({ length: 12 }).map((_, index) => ({
      puesto: index + 1,
      dependencia_id: `d-${index}`,
      comisaria: `Comisaría ${index}`,
      intervenciones: 100 - index,
      variacion_abs: 0,
      variacion_pct: 0,
      puesto_previo: 0,
    }));
    expect(normalizeRanking(items)).toHaveLength(10);
  });

  it("acepta un KPI sin referencia (has_reference=false)", () => {
    const snap = structuredClone(makeSnapshot()) as unknown as {
      payload: {
        kpis: Record<string, Kpi & { has_reference: boolean; delta_abs: null; delta_pct: null }>;
      };
    };
    snap.payload.kpis.armas_secuestradas.has_reference = false;
    snap.payload.kpis.armas_secuestradas.delta_abs = null;
    snap.payload.kpis.armas_secuestradas.delta_pct = null;
    const result = validateSnapshotMessage(snap);
    expect(result.ok).toBe(true);
    if (result.ok) {
      expect(result.message.payload.kpis.armas_secuestradas.has_reference).toBe(false);
      expect(result.message.payload.kpis.armas_secuestradas.delta_abs).toBeNull();
    }
  });
});
