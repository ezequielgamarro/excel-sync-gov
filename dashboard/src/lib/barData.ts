/**
 * Datasets de barras a partir de datos REALES (sin multiplicadores ni semillas).
 *
 * - `buildRegionalBars` / `buildTurnoBars`: derivan del snapshot (`regional` /
 *   `turnos`) tal cual. La variación sólo se muestra cuando el período elegido
 *   tiene histórico real («ayer»); en el resto queda en `null` / «—».
 * - `buildGroupBars`: deriva de una agrupación real de CONSULTAS
 *   (Resultado/Causas/Jefatura Regional/Turno). No hay base histórica asociada,
 *   por lo que `baseline`/`deltaPct` son `null`.
 */

import type { ComparisonPeriod } from "./comparison";
import type { ConsultaGroup, KpiDirection, RegionalItem, TurnoItem, TurnoEstado } from "../types";

export interface BarFilters {
  turno: string;
  unidad: string;
  rango: string;
}

export interface BarDatum {
  id: string;
  label: string;
  value: number;
  /** Base histórica real; `null` si no existe referencia. */
  baseline: number | null;
  deltaAbs: number | null;
  deltaPct: number | null;
  direction: KpiDirection;
  highlight: boolean;
  estado?: TurnoEstado;
}

function directionOf(deltaAbs: number | null): KpiDirection {
  if (deltaAbs === null) return "flat";
  if (deltaAbs > 0) return "up";
  if (deltaAbs < 0) return "down";
  return "flat";
}

/** ¿El período pedido tiene comparación real en el snapshot? */
function hasComparison(period: ComparisonPeriod): boolean {
  return period === "ayer";
}

/** Intervenciones por Unidad Regional (datos reales del snapshot). */
export function buildRegionalBars(
  regional: RegionalItem[],
  filters: BarFilters,
  period: ComparisonPeriod = "ayer",
): BarDatum[] {
  const anySelected = filters.unidad !== "TODAS";
  const withComparison = hasComparison(period);
  return regional.map((item) => {
    const deltaAbs = withComparison ? item.variacion_abs : null;
    const deltaPct = withComparison ? item.variacion_pct : null;
    return {
      id: item.unidad_id,
      label: item.label,
      value: Math.max(0, item.intervenciones),
      baseline: deltaAbs === null ? null : Math.max(0, item.intervenciones - deltaAbs),
      deltaAbs,
      deltaPct,
      direction: directionOf(deltaAbs),
      highlight: anySelected && item.unidad_id === filters.unidad,
    };
  });
}

/** Barras por turno operativo (datos reales del snapshot). */
export function buildTurnoBars(
  turnos: TurnoItem[],
  filters: BarFilters,
  period: ComparisonPeriod = "ayer",
): BarDatum[] {
  const anySelected = filters.turno !== "TODOS";
  const withComparison = hasComparison(period);
  return turnos.map((item) => {
    const deltaAbs = withComparison ? item.variacion_abs : null;
    const deltaPct = withComparison ? item.variacion_pct : null;
    return {
      id: item.turno_id,
      label: item.label,
      value: Math.max(0, item.intervenciones),
      baseline: deltaAbs === null ? null : Math.max(0, item.intervenciones - deltaAbs),
      deltaAbs,
      deltaPct,
      direction: directionOf(deltaAbs),
      highlight: anySelected && item.turno_id === filters.turno,
      estado: item.estado,
    };
  });
}

/**
 * Barras a partir de una agrupación real de CONSULTAS (Resultado/Causas/
 * Jefatura Regional/Turno). Sin base histórica asociada: `baseline` es `null`.
 */
export function buildGroupBars(groups: ConsultaGroup[], limit = 8): BarDatum[] {
  return groups.slice(0, limit).map((group) => ({
    id: group.key || group.label,
    label: group.label,
    value: Math.max(0, group.value),
    baseline: null,
    deltaAbs: null,
    deltaPct: null,
    direction: "flat",
    highlight: false,
  }));
}
