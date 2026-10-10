/**
 * Validación defensiva del sobre WSS (T51, §2.2.5, §7.8).
 *
 * - Versión `schema_version` mayor no soportada → error de esquema (banner
 *   `ACTUALIZACIÓN REQUERIDA`).
 * - Campos obligatorios ausentes o tipos inválidos → se rechaza el evento
 *   completo (fail-closed, §7.8).
 * - KPI negativo/no numérico/NaN/Infinity → se rechaza la instantánea completa
 *   y se muestra `DATOS NO VÁLIDOS` (RF-02.i).
 * - Unidad regional fuera de la allowlist de 5 → se descarta y se audita como
 *   `rejected_unknown_unit` (RF-03.h); la categoría canónica se mantiene.
 */

import {
  KPI_ORDER,
  SUPPORTED_SCHEMA_MAJOR,
  TURNO_ORDER,
  UNIDAD_LABEL,
  UNIDAD_ORDER,
  type KpiKey,
  type RankingItem,
  type RegionalItem,
  type SnapshotMessage,
  type TurnoId,
  type TurnoItem,
  type UnidadId,
} from "../types";

export interface ValidateSuccess {
  ok: true;
  message: SnapshotMessage;
  warnings: string[];
}

export interface ValidateFailure {
  ok: false;
  reason: "invalid" | "schema_unsupported";
  detail: string;
}

export type ValidateResult = ValidateSuccess | ValidateFailure;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isFiniteNonNegativeInt(value: unknown): value is number {
  return (
    typeof value === "number" && Number.isFinite(value) && Number.isInteger(value) && value >= 0
  );
}

function schemaMajor(version: string): number {
  const major = Number.parseInt(version.split(".")[0] ?? "", 10);
  return Number.isFinite(major) ? major : -1;
}

/** Normaliza el ranking: desc por intervenciones, desempate alfabético, ≤ 10. */
export function normalizeRanking(items: RankingItem[]): RankingItem[] {
  return [...items]
    .sort((a, b) => {
      if (b.intervenciones !== a.intervenciones) return b.intervenciones - a.intervenciones;
      return a.comisaria.localeCompare(b.comisaria, "es");
    })
    .slice(0, 10)
    .map((item, index) => ({ ...item, puesto: index + 1 }));
}

/**
 * Valida y normaliza el mensaje. No lanza: devuelve un resultado discriminado.
 */
export function validateSnapshotMessage(raw: unknown): ValidateResult {
  if (!isRecord(raw)) return { ok: false, reason: "invalid", detail: "mensaje no objeto" };
  if (raw.type !== "indicators.snapshot") {
    return { ok: false, reason: "invalid", detail: "type no es indicators.snapshot" };
  }
  const version = typeof raw.schema_version === "string" ? raw.schema_version : "";
  if (schemaMajor(version) > SUPPORTED_SCHEMA_MAJOR || schemaMajor(version) < 0) {
    return {
      ok: false,
      reason: "schema_unsupported",
      detail: `schema_version ${version || "?"} no soportada`,
    };
  }
  const seq = raw.seq;
  if (!isFiniteNonNegativeInt(seq)) return { ok: false, reason: "invalid", detail: "seq inválido" };
  const eventId = typeof raw.event_id === "string" ? raw.event_id : "";
  if (!eventId) return { ok: false, reason: "invalid", detail: "event_id ausente" };

  const payload = raw.payload;
  if (!isRecord(payload)) return { ok: false, reason: "invalid", detail: "payload ausente" };
  const warnings: string[] = [];

  // --- KPIs: los 4 obligatorios y válidos (RF-02.i). ---
  const kpisRaw = payload.kpis;
  if (!isRecord(kpisRaw)) return { ok: false, reason: "invalid", detail: "payload.kpis ausente" };
  const kpis = {} as SnapshotMessage["payload"]["kpis"];
  for (const key of KPI_ORDER) {
    const kpi = kpisRaw[key];
    if (!isRecord(kpi)) {
      return { ok: false, reason: "invalid", detail: `KPI ${key} ausente` };
    }
    if (!isFiniteNonNegativeInt(kpi.value)) {
      return { ok: false, reason: "invalid", detail: `KPI ${key} inválido (negativo/NaN)` };
    }
    const deltaAbs = kpi.delta_abs;
    const deltaPct = kpi.delta_pct;
    if (deltaAbs !== null && !Number.isFinite(deltaAbs as number)) {
      return { ok: false, reason: "invalid", detail: `KPI ${key} delta_abs inválido` };
    }
    if (deltaPct !== null && !Number.isFinite(deltaPct as number)) {
      return { ok: false, reason: "invalid", detail: `KPI ${key} delta_pct inválido` };
    }
    const direction = kpi.direction;
    if (direction !== "up" && direction !== "down" && direction !== "flat") {
      return { ok: false, reason: "invalid", detail: `KPI ${key} direction inválido` };
    }
    kpis[key as KpiKey] = {
      label: typeof kpi.label === "string" ? kpi.label : key,
      value: kpi.value,
      delta_abs: (deltaAbs as number | null) ?? null,
      delta_pct: (deltaPct as number | null) ?? null,
      direction,
      comparison: "ayer_mismo_tramo",
      baseline_value: isFiniteNonNegativeInt(kpi.baseline_value) ? kpi.baseline_value : 0,
      as_of: typeof kpi.as_of === "string" ? kpi.as_of : "",
      has_reference: kpi.has_reference === true,
    };
  }

  // --- Regional: descartar unidades fuera de la allowlist (RF-03.h). ---
  const regionalRaw = Array.isArray(payload.regional) ? payload.regional : [];
  const byUnit = new Map<UnidadId, RegionalItem>();
  for (const item of regionalRaw) {
    if (!isRecord(item)) continue;
    const unidadId = item.unidad_id;
    if (typeof unidadId !== "string" || !UNIDAD_ORDER.includes(unidadId as UnidadId)) {
      warnings.push(`rejected_unknown_unit:${String(unidadId)}`);
      continue;
    }
    if (!isFiniteNonNegativeInt(item.intervenciones)) continue;
    byUnit.set(unidadId as UnidadId, {
      unidad_id: unidadId as UnidadId,
      label: UNIDAD_LABEL[unidadId as UnidadId],
      intervenciones: item.intervenciones,
      variacion_abs: Number.isFinite(item.variacion_abs as number)
        ? (item.variacion_abs as number)
        : 0,
      variacion_pct: Number.isFinite(item.variacion_pct as number)
        ? (item.variacion_pct as number)
        : 0,
      rank: isFiniteNonNegativeInt(item.rank) ? item.rank : 0,
    });
  }
  // Categoría sin datos → barra 0 + "sin datos" (RF-03.e); orden canónico.
  const regional: RegionalItem[] = UNIDAD_ORDER.map(
    (unit) =>
      byUnit.get(unit) ?? {
        unidad_id: unit,
        label: UNIDAD_LABEL[unit],
        intervenciones: 0,
        variacion_abs: 0,
        variacion_pct: 0,
        rank: 0,
      },
  );

  // --- Turnos: orden cronológico canónico; si falta uno, se sintetiza. ---
  const turnosRaw = Array.isArray(payload.turnos) ? payload.turnos : [];
  const turnoById = new Map<TurnoId, TurnoItem>();
  for (const item of turnosRaw) {
    if (!isRecord(item)) continue;
    const turnoId = item.turno_id;
    if (typeof turnoId !== "string" || !TURNO_ORDER.includes(turnoId as TurnoId)) continue;
    if (!isFiniteNonNegativeInt(item.intervenciones)) continue;
    const estado = item.estado;
    turnoById.set(turnoId as TurnoId, {
      turno_id: turnoId as TurnoId,
      inicio_min: Number.isFinite(item.inicio_min as number) ? (item.inicio_min as number) : 0,
      fin_min: Number.isFinite(item.fin_min as number) ? (item.fin_min as number) : 0,
      label: typeof item.label === "string" ? item.label : (turnoId as string),
      intervenciones: item.intervenciones,
      variacion_abs: Number.isFinite(item.variacion_abs as number)
        ? (item.variacion_abs as number)
        : 0,
      variacion_pct: Number.isFinite(item.variacion_pct as number)
        ? (item.variacion_pct as number)
        : 0,
      estado: estado === "en_curso" || estado === "cerrada" ? estado : "pendiente",
    });
  }
  const turnos: TurnoItem[] = TURNO_ORDER.map(
    (id) =>
      turnoById.get(id) ?? {
        turno_id: id,
        inicio_min: 0,
        fin_min: 0,
        label: id,
        intervenciones: 0,
        variacion_abs: 0,
        variacion_pct: 0,
        estado: "pendiente",
      },
  );

  // --- Ranking: hasta 10, orden determinista. ---
  const rankingRaw = payload.ranking;
  const depRaw =
    isRecord(rankingRaw) && Array.isArray(rankingRaw.dependencias) ? rankingRaw.dependencias : [];
  const dependencias: RankingItem[] = [];
  for (const item of depRaw) {
    if (!isRecord(item)) continue;
    if (!isFiniteNonNegativeInt(item.intervenciones)) continue;
    dependencias.push({
      puesto: isFiniteNonNegativeInt(item.puesto) ? item.puesto : 0,
      dependencia_id: typeof item.dependencia_id === "string" ? item.dependencia_id : "",
      comisaria: typeof item.comisaria === "string" ? item.comisaria : "",
      intervenciones: item.intervenciones,
      variacion_abs: Number.isFinite(item.variacion_abs as number)
        ? (item.variacion_abs as number)
        : 0,
      variacion_pct: Number.isFinite(item.variacion_pct as number)
        ? (item.variacion_pct as number)
        : 0,
      puesto_previo: isFiniteNonNegativeInt(item.puesto_previo) ? item.puesto_previo : 0,
    });
  }

  // --- Freshness / quality. ---
  const freshnessRaw = isRecord(payload.freshness) ? payload.freshness : {};
  const qualityRaw = isRecord(payload.quality) ? payload.quality : {};

  const message: SnapshotMessage = {
    schema_version: version,
    type: "indicators.snapshot",
    event_id: eventId,
    seq,
    room_id: typeof raw.room_id === "string" ? raw.room_id : "",
    ts: typeof raw.ts === "string" ? raw.ts : "",
    tz: typeof raw.tz === "string" ? raw.tz : "America/Argentina/Buenos_Aires",
    tz_offset_minutes: Number.isFinite(raw.tz_offset_minutes as number)
      ? (raw.tz_offset_minutes as number)
      : undefined,
    data_date: typeof raw.data_date === "string" ? raw.data_date : "",
    source: isRecord(raw.source)
      ? {
          webhook_id: String(raw.source.webhook_id ?? ""),
          doc_id: String(raw.source.doc_id ?? ""),
          content_sha256: String(raw.source.content_sha256 ?? ""),
          sheet_modified_at: String(raw.source.sheet_modified_at ?? ""),
        }
      : { webhook_id: "", doc_id: "", content_sha256: "", sheet_modified_at: "" },
    payload: {
      kpis,
      regional,
      turnos,
      ranking: { top_n: 10, dependencias: normalizeRanking(dependencias) },
      freshness: {
        last_event_ts:
          typeof freshnessRaw.last_event_ts === "string" ? freshnessRaw.last_event_ts : "",
        sheet_modified_at:
          typeof freshnessRaw.sheet_modified_at === "string"
            ? freshnessRaw.sheet_modified_at
            : undefined,
        stale: freshnessRaw.stale === true,
        age_seconds: Number.isFinite(freshnessRaw.age_seconds as number)
          ? (freshnessRaw.age_seconds as number)
          : undefined,
      },
      quality: {
        partial: qualityRaw.partial === true,
        motivo: typeof qualityRaw.motivo === "string" ? qualityRaw.motivo : undefined,
        source_rows: Number.isFinite(qualityRaw.source_rows as number)
          ? (qualityRaw.source_rows as number)
          : undefined,
        warnings: Array.isArray(qualityRaw.warnings)
          ? (qualityRaw.warnings as unknown[]).map(String)
          : [],
      },
    },
    correlation_id: typeof raw.correlation_id === "string" ? raw.correlation_id : "",
  };

  return { ok: true, message, warnings };
}
