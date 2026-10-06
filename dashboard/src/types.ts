/**
 * Tipos del contrato de mensaje `indicators.snapshot` v1.0.0
 * (`contracts/messages/1.0.0.schema.json`, SPEC-001 §7.2–§7.7).
 *
 * El cliente valida defensivamente la forma del mensaje (§2.2.5): rechaza el
 * evento completo ante tipos inválidos y descarta campos desconocidos.
 */

export const SUPPORTED_SCHEMA_MAJOR = 1;
export const SCHEMA_VERSION = "1.0.0";

export type KpiDirection = "up" | "down" | "flat";
export type TurnoEstado = "pendiente" | "en_curso" | "cerrada";
export type TurnoId = "MAÑANA" | "TARDE" | "NOCHE";
export type UnidadId = "capital" | "sur" | "este" | "oeste" | "norte";

export interface Kpi {
  label: string;
  value: number;
  delta_abs: number | null;
  delta_pct: number | null;
  direction: KpiDirection;
  comparison: "ayer_mismo_tramo";
  baseline_value: number;
  as_of: string;
  has_reference: boolean;
}

export type KpiKey =
  | "total_consultas_sifcop"
  | "personas_capturadas"
  | "vehiculos_secuestrados"
  | "armas_secuestradas";

export interface RegionalItem {
  unidad_id: UnidadId;
  label: string;
  intervenciones: number;
  variacion_abs: number;
  variacion_pct: number;
  rank: number;
}

export interface TurnoItem {
  turno_id: TurnoId;
  inicio_min: number;
  fin_min: number;
  label: string;
  intervenciones: number;
  variacion_abs: number;
  variacion_pct: number;
  estado: TurnoEstado;
}

export interface RankingItem {
  puesto: number;
  dependencia_id: string;
  comisaria: string;
  intervenciones: number;
  variacion_abs: number;
  variacion_pct: number;
  puesto_previo: number;
}

export interface Freshness {
  last_event_ts: string;
  sheet_modified_at?: string;
  stale: boolean;
  age_seconds?: number;
}

export interface Quality {
  partial: boolean;
  motivo?: string;
  source_rows?: number;
  warnings?: string[];
}

export interface SnapshotPayload {
  kpis: Record<KpiKey, Kpi>;
  regional: RegionalItem[];
  turnos: TurnoItem[];
  ranking: { top_n: number; dependencias: RankingItem[] };
  freshness: Freshness;
  quality: Quality;
}

export interface SnapshotSource {
  webhook_id: string;
  doc_id: string;
  content_sha256: string;
  sheet_modified_at: string;
}

export interface SnapshotMessage {
  schema_version: string;
  type: "indicators.snapshot";
  event_id: string;
  seq: number;
  room_id: string;
  ts: string;
  tz: string;
  tz_offset_minutes?: number;
  data_date: string;
  source: SnapshotSource;
  payload: SnapshotPayload;
  correlation_id: string;
}

export interface HelloMessage {
  type: "hello";
  room_id: string;
  schema_version: string;
  server_ts: string;
  last_seq: number;
  heartbeat_interval_s: number;
}

export interface HeartbeatMessage {
  type: "heartbeat";
  server_ts: string;
  seq_hint: number;
}

export interface ErrorMessage {
  type: "error";
  code: string;
  correlation_id?: string;
}

export type ServerMessage = SnapshotMessage | HelloMessage | HeartbeatMessage | ErrorMessage;

/** Orden canónico de las 4 tarjetas KPI (RF-02.a/b). */
export const KPI_ORDER: readonly KpiKey[] = [
  "total_consultas_sifcop",
  "personas_capturadas",
  "vehiculos_secuestrados",
  "armas_secuestradas",
] as const;

/**
 * Etiquetas institucionales EXACTAS de las tarjetas KPI.
 *
 * Mapeo de presentación en el frontend (no se reescribe el `label` del
 * contrato/backend): el catálogo cerrado manda sobre el texto del snapshot
 * para garantizar la nomenclatura oficial de la sala.
 */
export const KPI_LABEL: Record<KpiKey, string> = {
  total_consultas_sifcop: "TOTAL CONSULTAS",
  personas_capturadas: "PERSONAS APREHENDIDAS POR CAUSAS JUDICIALES",
  vehiculos_secuestrados: "VEHÍCULOS SECUESTRADOS POR CAUSAS JUDICIALES",
  armas_secuestradas: "ARMAS DE FUEGO SECUESTRADAS POR CAUSAS JUDICIALES",
};

/** @deprecated usar `KPI_LABEL`; se conserva por compatibilidad. */
export const KPI_FALLBACK_LABEL: Record<KpiKey, string> = KPI_LABEL;

/** Catálogo cerrado de 5 unidades y orden canónico territorial (RF-03.b). */
export const UNIDAD_ORDER: readonly UnidadId[] = [
  "capital",
  "sur",
  "este",
  "oeste",
  "norte",
] as const;

export const UNIDAD_LABEL: Record<UnidadId, string> = {
  capital: "Capital",
  sur: "Sur",
  este: "Este",
  oeste: "Oeste",
  norte: "Norte",
};

/** Orden cronológico de los 3 turnos (RF-04.a). */
export const TURNO_ORDER: readonly TurnoId[] = ["MAÑANA", "TARDE", "NOCHE"] as const;

export const TURNO_LABEL: Record<TurnoId, string> = {
  MAÑANA: "MAÑANA",
  TARDE: "TARDE",
  NOCHE: "NOCHE",
};

export interface RankingRow {
  puesto: number;
  dependenciaId: string;
  comisaria: string;
  intervenciones: number;
  variacionAbs: number;
  variacionPct: number;
  puestoPrevio: number;
}

/**
 * Orden exacto de las 20 columnas de la hoja «CONSULTAS» de la planilla oficial
 * de la Jefatura (espejo de `backend/app/models/tables.py`).
 */
export const CONSULTA_COLUMNS = [
  "fecha_consulta",
  "hora_consulta",
  "turno",
  "jerarquia",
  "personal_policial",
  "jefatura_regional",
  "dependencias",
  "tipo_consulta",
  "identificacion",
  "tipo_arma_vehiculo",
  "resultado",
  "causas_penales",
  "registro_legajo",
  "autoridad_judicial",
  "sistema_utilizado",
  "tramite_devuelto",
  "hora_resp",
  "personal_que_informa",
  "cargo",
  "operativos_preventivos",
] as const;

export type ConsultaColumn = (typeof CONSULTA_COLUMNS)[number];

/** Fila normalizada de la hoja «CONSULTAS» (contrato de ingesta). */
export interface ConsultaRow {
  fecha_consulta: string;
  hora_consulta: string;
  turno: string;
  jerarquia: string;
  personal_policial: string;
  jefatura_regional: string;
  dependencias: string;
  tipo_consulta: string;
  identificacion: string;
  tipo_arma_vehiculo: string;
  resultado: string;
  causas_penales: string;
  registro_legajo: string;
  autoridad_judicial: string;
  sistema_utilizado: string;
  tramite_devuelto: string;
  hora_resp: string;
  personal_que_informa: string;
  cargo: string;
  operativos_preventivos: string;
}

/** Conteo de una categoría (Resultado/Causa/Jefatura/Turno). */
export interface ConsultaGroup {
  key: string;
  label: string;
  value: number;
}

/** KPIs derivados de la agrupación de CONSULTAS. */
export interface ConsultaKpis {
  total_consultas: number;
  personas_aprehendidas: number;
  vehiculos_secuestrados: number;
  armas_secuestradas: number;
}

/** Agregación de CONSULTAS devuelta por `GET /dashboard/consultas`. */
export interface ConsultaAggregation {
  meta: {
    rango: string;
    turno: string;
    unidad: string;
    resultado: string;
    causa: string;
    total: number;
  };
  kpis: ConsultaKpis;
  by_resultado: ConsultaGroup[];
  by_causas_penales: ConsultaGroup[];
  by_jefatura_regional: ConsultaGroup[];
  by_turno: ConsultaGroup[];
  series: Array<{ ts: string; value: number }>;
}

/**
 * Celda de una fila de la planilla de hospitales: la primera columna es texto
 * (localidad) y el resto columnas numéricas (causas delictivas).
 */
export type HospitalCell = string | number | null;

/** Fila dinámica clave → valor de la planilla de hospitales. */
export interface HospitalRow {
  [column: string]: HospitalCell;
}

/** Punto de la serie del gráfico de causas. */
export interface HospitalCauseDatum {
  causa: string;
  cantidad: number;
}

/** Respuesta de `GET /api/hospitales/estadisticas` (columnas dinámicas). */
export interface HospitalesEstadisticas {
  sheet: string;
  columns: string[];
  rows: HospitalRow[];
  total_rows: number;
  /** Totales de las causas clave (claves normalizadas `snake_case`). */
  kpis?: Record<string, number>;
  /** Serie para el gráfico (una entrada por columna numérica, sin ceros). */
  chartData?: HospitalCauseDatum[];
}

/** KPI derivado de una columna de la planilla de hospitales. */
export interface HospitalKpi {
  key: string;
  label: string;
  value: number;
  /** Columna real de la que se sumó; `null` si no existe en el origen. */
  column: string | null;
}

/** Punto (`name`/`value`) de una serie de la hoja `DASHBOARD_WEB`. */
export interface EstadisticaItem {
  name: string;
  value: number;
}

/** Fila del «Ranking Top 5» con variación real actual vs período anterior. */
export interface RankingTop5Item {
  name: string;
  /** Conteo real de la ventana ACTUAL (alias de `value`). */
  intervenciones: number;
  /** Alias de `intervenciones` (compatibilidad con las series `{name,value}`). */
  value: number;
  /** Diferencia absoluta actual − anterior. */
  variacion_abs: number;
  /** Variación porcentual; `null` si no hay base anterior > 0 (nunca 0). */
  variacion_pct: number | null;
}

/** KPIs agregados de la hoja `CONSULTAS` (enteros, NaN/vacíos → 0). */
export interface EstadisticasKpis {
  total_consultas: number;
  /** Aprehendidos (hoja `Positivos` o PERSONA + POSITIVO). */
  aprehendidos?: number;
  personas: number;
  vehiculos: number;
  armas: number;
  positivos: number;
  negativos: number;
}

/** Totales reales exactos del workbook (`CONSULTAS`). */
export interface EstadisticasTotales {
  total_consultas: number;
  aprehendidos: number;
  vehiculos_secuestrados: number;
  armas_secuestradas: number;
}

/** KPIs reales de un mes (`por_mes`). */
export interface EstadisticasMes {
  /** Mes ISO `YYYY-MM`. */
  mes: string;
  total_consultas: number;
  aprehendidos: number;
  vehiculos: number;
  armas: number;
}

/** Incidentes de un día desglosados por turno operativo. */
export interface IncidentesTurnoDia {
  /** Día `DD/MM`. */
  fecha: string;
  mañana: number;
  tarde: number;
  noche: number;
}

/** Total de incidentes de un día (evolución diaria estricta por columna Fecha). */
export interface IncidenteFecha {
  /** Día `DD/MM`. */
  fecha: string;
  total: number;
}

/**
 * Respuesta de `GET /api/estadisticas`: series reales del workbook de la
 * Policía (`DASHBOARD_WEB` + `CONSULTAS` + `Data`/`ESTADISTICAS`).
 *
 * Las 3 claves históricas (regionales, dependencias, resultados) conservan el
 * mismo formato; las demás alimentan Incidentes, Logística y Comparativas.
 * Ante error, el cuerpo trae `estado: "error"` y `detalle` (nunca datos
 * inventados); una hoja/clave ausente llega como arreglo vacío.
 */
export interface EstadisticasRespuesta {
  estado: "exito" | "error";
  grafico_regionales?: EstadisticaItem[];
  grafico_dependencias?: EstadisticaItem[];
  alertas_resultados?: EstadisticaItem[];
  /** Alias de `grafico_regionales` (gráfico «Intervenciones por Unidad»). */
  intervenciones_por_unidad?: EstadisticaItem[];
  /** Alias de `grafico_dependencias` (gráfico «Consultas por Dependencia»). */
  consultas_por_dependencia?: EstadisticaItem[];
  /** Evolución diaria estricta: `[{fecha: "DD/MM", total}]` cronológico. */
  incidentes_por_fecha?: IncidenteFecha[];
  /** Incidentes por día (ISO `YYYY-MM-DD`, orden cronológico). */
  incidentes_por_dia?: EstadisticaItem[];
  /** Incidentes por hora del día (`HH:00`). */
  incidentes_por_hora?: EstadisticaItem[];
  /** Incidentes por tipo de consulta (PERSONA/VEHICULO/ARMA). */
  incidentes_por_tipo?: EstadisticaItem[];
  /** Incidentes agregados por unidad regional. */
  incidentes_por_regional?: EstadisticaItem[];
  /** Incidentes agregados por dependencia. */
  incidentes_por_dependencia?: EstadisticaItem[];
  /** Incidentes por resultado (POSITIVO/NEGATIVO). */
  incidentes_por_resultado?: EstadisticaItem[];
  /** Incidentes por jerarquía del personal interviniente. */
  incidentes_por_jerarquia?: EstadisticaItem[];
  /** Distribución de incidentes por tipo (donut). */
  distribucion_incidentes?: EstadisticaItem[];
  /** Logística: vehículos secuestrados por unidad regional. */
  logistica_vehiculos_por_regional?: EstadisticaItem[];
  /** Logística: vehículos por dependencia. */
  logistica_vehiculos_por_dependencia?: EstadisticaItem[];
  /** Logística: armas por unidad regional. */
  logistica_armas_por_regional?: EstadisticaItem[];
  /** Logística: armas por dependencia. */
  logistica_armas_por_dependencia?: EstadisticaItem[];
  /** Alias de `logistica_vehiculos_por_regional` (gráfico de vehículos). */
  vehiculosPorRegional?: EstadisticaItem[];
  /** Alias de `logistica_armas_por_regional` (gráfico de armas). */
  armasPorRegional?: EstadisticaItem[];
  /** Comparativas (serie principal: totales mensuales). */
  comparativas?: EstadisticaItem[];
  /** Comparativas semanales (`Data`: mes + semana). */
  comparativas_semanales?: EstadisticaItem[];
  /** Comparativas mensuales (totales por mes). */
  comparativas_mensuales?: EstadisticaItem[];
  /** KPIs agregados de `CONSULTAS`. */
  kpis?: EstadisticasKpis;
  /** Totales reales exactos (consultas, aprehendidos, vehículos y armas). */
  totales?: EstadisticasTotales;
  /** KPIs reales por mes (orden cronológico). */
  por_mes?: EstadisticasMes[];
  /** Serie `[{name: "YYYY-MM", value}]` de consultas por mes (charts). */
  consultas_por_mes?: EstadisticaItem[];
  /** Ranking Top 5 de dependencias (orden descendente, con variación real). */
  rankingTop5?: RankingTop5Item[];
  /** Lista única/ordenada de Unidades Regionales presentes (selectores). */
  regionales_disponibles?: string[];
  /** Lista única/ordenada de dependencias presentes (selectores). */
  dependencias_disponibles?: string[];
  /** Incidentes por día y turno (`fecha` DD/MM + mañana/tarde/noche). */
  incidentes_turno_por_dia?: IncidentesTurnoDia[];
  /** Totales de la hoja `ESTADISTICAS` (mes/general). */
  estadisticas_totales?: { total_mes?: number; total_general?: number };
  /** Hojas del workbook realmente detectadas (diagnóstico). */
  hojas?: string[];
  detalle?: string;
}
