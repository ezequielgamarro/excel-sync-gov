/**
 * Derivación de KPIs y distribuciones a partir de la respuesta cruda de
 * `GET /api/hospitales/estadisticas`.
 *
 * La planilla entrega columnas **dinámicas**: la primera columna es la
 * localidad (texto) y el resto son causas delictivas (numéricas). Todas las
 * funciones toleran columnas ausentes (se resuelven contra `columns` por
 * nombre normalizado) y valores no numéricos (se tratan como 0).
 */

import type { HospitalesEstadisticas, HospitalKpi, HospitalRow } from "../types";

/** Definición de un KPI: clave estable, etiqueta y alias de columna. */
export interface HospitalKpiDef {
  key: string;
  label: string;
  aliases: string[];
}

/**
 * KPIs clave del módulo. Los tres primeros son los exigidos; `Homicidios` y
 * `Femicidio` se agregan cuando la planilla los expone (si no, valen 0).
 */
export const HOSPITAL_KPI_DEFS: readonly HospitalKpiDef[] = [
  {
    key: "lesiones_culposas",
    label: "Total Lesiones Culposas",
    aliases: ["lesiones culposas"],
  },
  {
    key: "heridos_arma_fuego",
    label: "Total Heridos Arma de Fuego",
    aliases: ["heridos con arma de fuego", "heridos arma de fuego"],
  },
  {
    key: "violencia_familiar",
    label: "Total Violencia Familiar",
    aliases: ["violencia familiar"],
  },
  { key: "homicidios", label: "Total Homicidios", aliases: ["homicidios"] },
  { key: "femicidio", label: "Total Femicidio", aliases: ["femicidio", "femicidios"] },
];

const ACCENT_MAP: Record<string, string> = {
  á: "a",
  é: "e",
  í: "i",
  ó: "o",
  ú: "u",
  ü: "u",
  ñ: "n",
};

/** `"Lesiones Culposas"` → `"lesiones culposas"` (sin acentos ni espacios extra). */
export function normalizeColumnName(value: string): string {
  return String(value)
    .toLowerCase()
    .replace(/[áéíóúüñ]/g, (char) => ACCENT_MAP[char] ?? char)
    .trim()
    .replace(/\s+/g, " ");
}

/** Devuelve la columna real cuyo nombre normalizado coincide con algún alias. */
export function resolveColumn(columns: string[], aliases: string[]): string | null {
  const normalized = new Map(columns.map((column) => [normalizeColumnName(column), column]));
  for (const alias of aliases) {
    const found = normalized.get(normalizeColumnName(alias));
    if (found) return found;
  }
  return null;
}

/** Convierte un valor de celda a número finito (no numérico → 0). */
export function numericValue(value: unknown): number {
  if (typeof value === "number") return Number.isFinite(value) ? value : 0;
  if (typeof value === "string" && value.trim() !== "") {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}

/** Suma una columna entera, ignorando celdas no numéricas. */
export function sumColumn(rows: HospitalRow[], column: string): number {
  return rows.reduce((total, row) => total + numericValue(row[column]), 0);
}

/** `"Heridos con arma de fuego"` → `"heridos_con_arma_de_fuego"`. */
export function normalizeKpiKey(value: string): string {
  return normalizeColumnName(value).replace(/\s+/g, "_");
}

/** Computa los KPIs clave tolerando columnas ausentes (→ 0). */
export function computeHospitalKpis(data: HospitalesEstadisticas): HospitalKpi[] {
  const kpis = data.kpis;
  return HOSPITAL_KPI_DEFS.map((def) => {
    const column = resolveColumn(data.columns, def.aliases);
    if (kpis) {
      // Mapea la clave del KPI a la clave normalizada que expone el backend.
      const candidates = [def.key, ...def.aliases.map(normalizeKpiKey)];
      const found = candidates.find((key) => key in kpis);
      if (found) {
        return { key: def.key, label: def.label, column, value: numericValue(kpis[found]) };
      }
    }
    return {
      key: def.key,
      label: def.label,
      column,
      value: column ? sumColumn(data.rows, column) : 0,
    };
  });
}
