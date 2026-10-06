/** Fixture mínimo del contrato 1.0.0 para pruebas (T51–T58). */

export function kpi(value: number, deltaAbs: number | null = 1, deltaPct: number | null = 1) {
  return {
    label: "KPI",
    value,
    delta_abs: deltaAbs,
    delta_pct: deltaPct,
    direction: deltaAbs === null ? "flat" : deltaAbs > 0 ? "up" : deltaAbs < 0 ? "down" : "flat",
    comparison: "ayer_mismo_tramo",
    baseline_value: Math.max(0, value - (deltaAbs ?? 0)),
    as_of: "2026-10-03T14:22:05Z",
    has_reference: deltaAbs !== null,
  };
}

export function makeSnapshot(overrides: Record<string, unknown> = {}): Record<string, unknown> {
  const base: Record<string, unknown> = {
    schema_version: "1.0.0",
    type: "indicators.snapshot",
    event_id: "018f1d2e-3a4b-7c5d-8e6f-0a1b2c3d4e5f",
    seq: 10,
    room_id: "sala-central",
    ts: "2026-10-03T14:22:05.412Z",
    tz: "America/Argentina/Buenos_Aires",
    tz_offset_minutes: -180,
    data_date: "2026-10-03",
    source: {
      webhook_id: "wh-sifcop-central",
      doc_id: "sifcop-resumen",
      content_sha256: "a".repeat(64),
      sheet_modified_at: "2026-10-03T14:21:58Z",
    },
    payload: {
      kpis: {
        total_consultas_sifcop: kpi(184732),
        personas_capturadas: kpi(4128),
        vehiculos_secuestrados: kpi(37),
        armas_secuestradas: kpi(12),
      },
      regional: [
        { unidad_id: "capital", label: "Capital", intervenciones: 268, variacion_abs: 22, variacion_pct: 8.93, rank: 1 },
        { unidad_id: "sur", label: "Sur", intervenciones: 142, variacion_abs: -5, variacion_pct: -3.4, rank: 2 },
        { unidad_id: "este", label: "Este", intervenciones: 98, variacion_abs: 7, variacion_pct: 7.74, rank: 3 },
        { unidad_id: "oeste", label: "Oeste", intervenciones: 71, variacion_abs: -3, variacion_pct: -4.05, rank: 4 },
        { unidad_id: "norte", label: "Norte", intervenciones: 34, variacion_abs: 1, variacion_pct: 3.03, rank: 5 },
      ],
      turnos: [
        { turno_id: "MAÑANA", inicio_min: 360, fin_min: 840, label: "MAÑANA (06-14)", intervenciones: 231, variacion_abs: 25, variacion_pct: 12.14, estado: "cerrada" },
        { turno_id: "TARDE", inicio_min: 840, fin_min: 1320, label: "TARDE (14-22)", intervenciones: 318, variacion_abs: 12, variacion_pct: 3.92, estado: "en_curso" },
        { turno_id: "NOCHE", inicio_min: 1320, fin_min: 360, label: "NOCHE (22-06)", intervenciones: 142, variacion_abs: -8, variacion_pct: -5.33, estado: "pendiente" },
      ],
      ranking: {
        top_n: 5,
        dependencias: [
          { puesto: 1, dependencia_id: "com-12", comisaria: "Comisaría 12", intervenciones: 94, variacion_abs: 12, variacion_pct: 14.63, puesto_previo: 2 },
          { puesto: 2, dependencia_id: "com-07", comisaria: "Comisaría 7", intervenciones: 88, variacion_abs: -4, variacion_pct: -4.35, puesto_previo: 1 },
        ],
      },
      freshness: { last_event_ts: "2026-10-03T14:22:05.412Z", stale: false, age_seconds: 0 },
      quality: { partial: false, source_rows: 5, warnings: [] },
    },
    correlation_id: "tr-test",
  };
  return { ...base, ...overrides };
}
