/**
 * Contrato compartido de los filtros globales y tokens visuales de los gráficos.
 *
 * Este módulo NO contiene generadores de datos: sólo tipos, valores por defecto
 * y la paleta. Los datos de los gráficos provienen siempre de fuentes reales
 * (Supabase `intervenciones_diarias` y snapshot).
 */

import type { TurnoId, UnidadId } from "../../types";

export type TurnoFilter = "TODOS" | TurnoId;
/**
 * Unidad Regional: «TODAS» + nombre oficial dinámico de Supabase
 * (`estadisticas.regionales_disponibles`, p. ej. «Unidad Regional Norte»).
 * El catálogo `UnidadId` se conserva como fallback estático.
 */
export type UnidadFilter = "TODAS" | UnidadId | (string & Record<never, never>);
export type RangoFilter = "24h" | "7d" | "30d";

export interface ActiveFilters {
  turno: TurnoFilter;
  unidad: UnidadFilter;
  rango: RangoFilter;
}

export const DEFAULT_FILTERS: ActiveFilters = {
  turno: "TODOS",
  unidad: "TODAS",
  rango: "30d",
};

/**
 * Paleta azul/cyan institucional para series de datos (barras/líneas/donas).
 * Deliberadamente SIN rojo/verde: `--neg`/`--pos` se reservan como acentos
 * semánticos de texto/borde, no como color de serie.
 */
export const CHART_PALETTE = ["#5161ff", "#4cc2ff", "#1e90ff", "#8fe3ff"] as const;
