/**
 * Adaptadores entre las series `{name, value}` de `GET /api/estadisticas` y la
 * forma que consumen los gráficos Recharts del panel (`ConsultaGroup` para
 * barras/donas y `{ts, value}` para la línea temporal).
 *
 * No hay generadores de datos: si la serie viene vacía o ausente, el resultado
 * es un arreglo vacío (la UI muestra «SIN DATOS», nunca demo).
 */

import type { ConsultaGroup, EstadisticaItem, IncidentesTurnoDia } from "../types";

/** Convierte una serie `[{name, value}]` en `ConsultaGroup[]` (key = label). */
export function aGrupos(items: EstadisticaItem[] | undefined | null): ConsultaGroup[] {
  return (items ?? []).map((item) => ({
    key: item.name,
    label: item.name,
    value: item.value,
  }));
}

/** Turnos operativos de `incidentes_turno_por_dia` (claves del backend). */
export type TurnoDiaKey = "mañana" | "tarde" | "noche";

/**
 * Extrae una serie `ConsultaGroup[]` por turno desde `incidentes_turno_por_dia`
 * (un punto por día) para graficar la evolución diaria. Sin datos → `[]`.
 */
export function aTurnoDia(
  items: IncidentesTurnoDia[] | undefined | null,
  turno: TurnoDiaKey,
): ConsultaGroup[] {
  return (items ?? []).map((item) => ({
    key: item.fecha,
    label: item.fecha,
    value: item[turno],
  }));
}

/**
 * Convierte una serie `[{name, value}]` en puntos `{ts, value}` para el gráfico
 * temporal. `name` debe ser una fecha ISO (`YYYY-MM-DD`); los valores no
 * numéricos se descartan para no romper el eje.
 */
export function aSerie(
  items: EstadisticaItem[] | undefined | null,
): Array<{ ts: string; value: number }> {
  return (items ?? [])
    .filter((item) => Number.isFinite(item.value))
    .map((item) => ({ ts: item.name, value: item.value }));
}
