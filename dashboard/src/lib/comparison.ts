/**
 * Períodos de comparación del tablero.
 *
 * El contrato del snapshot sólo aporta comparación real contra «ayer mismo
 * tramo» (`comparison: "ayer_mismo_tramo"`). Para el resto de períodos
 * (semana/mes/año) NO existe histórico en la fuente, por lo que la variación y
 * la base se exponen como `null` / «—» y nunca se fabrican con semillas.
 */

import type { Kpi } from "../types";

export type ComparisonPeriod = "ayer" | "semana" | "mes" | "anio";

export const COMPARISON_PERIODS: readonly ComparisonPeriod[] = [
  "ayer",
  "semana",
  "mes",
  "anio",
];

export const COMPARISON_LABEL: Record<ComparisonPeriod, string> = {
  ayer: "Ayer",
  semana: "Semana anterior",
  mes: "Mes anterior",
  anio: "Año anterior",
};

/** `true` sólo si la fuente tiene histórico real para el período elegido. */
export function hasRealComparison(period: ComparisonPeriod): boolean {
  return period === "ayer";
}

/**
 * Devuelve el KPI con la comparación real del período. Sólo «ayer» tiene
 * referencia en el snapshot; en el resto se marca `has_reference = false` y se
 * anulan delta/base para que la tarjeta muestre «—».
 */
export function buildComparisonKpi(kpi: Kpi, period: ComparisonPeriod): Kpi {
  if (hasRealComparison(period)) return kpi;
  return {
    ...kpi,
    baseline_value: kpi.value,
    delta_abs: null,
    delta_pct: null,
    direction: "flat",
    has_reference: false,
  };
}
