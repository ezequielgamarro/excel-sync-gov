/**
 * Hook de datos REACTIVO de las intervenciones (Supabase
 * `intervenciones_diarias`). Carga al montar las filas que cubren la ventana
 * actual y la de comparación, y deriva la forma interna
 * (`IntervencionesDerivadas`) con `derivarEstadisticas` según los filtros.
 * Expone `{ fase, datos, error, refetch }`, siguiendo el patrón de
 * `useDashboard`/`useConsultas` (skeletons en `"cargando"`).
 *
 * Los filtros nativos de Supabase (jefatura regional y `fecha_consulta`)
 * limitan la consulta; la derivación completa (comparativas, ranking, KPIs)
 * sigue ocurriendo en `derivarEstadisticas` sobre las filas traídas.
 *
 * NO existe respaldo con datos de demostración: ante error de red/consulta la
 * fase es `"error"` y `datos` queda `null`.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { supabase } from "../supabaseClient";
import { INTERVENCIONES_REFRESH_EVENT } from "../data/importarIntervenciones";
import { recolectarTodas } from "../data/api";
import { esJefaturaCatalogada } from "../data/dependencias";
import type { Intervencion } from "../data/api";
import { derivarEstadisticas } from "../lib/intervenciones";
import type { IntervencionesDerivadas } from "../lib/intervenciones";
import type { ComparisonPeriod } from "../lib/comparison";

export type FaseIntervenciones = "cargando" | "listo" | "error";

export interface UseIntervencionesOpciones {
  /** Unidad Regional exacta; `"TODAS"`/ausente no filtra. */
  unidad?: string;
  /** Rango de fechas (`"24h"`, `"7d"`, `"30d"`). */
  rango?: string;
  /** Período de comparación para variaciones y ranking. */
  period?: ComparisonPeriod;
}

export interface UseIntervencionesResult {
  fase: FaseIntervenciones;
  datos: IntervencionesDerivadas | null;
  error: string | null;
  /** Fuerza una recarga inmediata (botón «Reintentar» del estado de error). */
  refetch: () => void;
}

/** Cadencia del polling reactivo (ms). */
export const INTERVENCIONES_POLL_MS = 60_000;

/** Días de la ventana actual por rango (`"24h"` → 1, `"7d"` → 7, `"30d"` → 30). */
const DIAS_ACTUALES: Readonly<Record<string, number>> = {
  "24h": 1,
  "7d": 7,
  "30d": 30,
};

/** Días de la ventana de comparación inmediatamente anterior. */
const DIAS_COMPARACION: Readonly<Record<ComparisonPeriod, number>> = {
  ayer: 1,
  semana: 7,
  mes: 30,
  anio: 365,
};

/** Formatea una fecha local como `YYYY-MM-DD` (sin desfase por zona horaria). */
function isoLocal(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

/** Sólo filtra por unidad cuando es un valor real distinto de `"TODAS"`. */
function unidadFiltrable(unidad?: string): string | null {
  const valor = unidad?.trim();
  if (!valor || valor.toUpperCase() === "TODAS") return null;
  return valor;
}

/** Catálogo completo (sin filtro de unidad) para los selectores dinámicos. */
interface Catalogos {
  regionales: string[];
  dependencias: string[];
}

/** Proyección mínima del catálogo (sólo las columnas de los selectores). */
type FilaCatalogo = Pick<Intervencion, "jefatura_regional" | "dependencia">;

/** Únicos no vacíos, ordenados alfabéticamente (misma lógica que la derivación). */
function unicosDe<T>(rows: T[], keyOf: (row: T) => string): string[] {
  const set = new Set<string>();
  for (const row of rows) {
    const key = keyOf(row);
    if (key !== "") set.add(key);
  }
  return Array.from(set).sort((a, b) => a.localeCompare(b));
}

export function useIntervenciones(
  opciones: UseIntervencionesOpciones = {},
): UseIntervencionesResult {
  const { unidad, rango, period } = opciones;
  const [rows, setRows] = useState<Intervencion[] | null>(null);
  const [catalogos, setCatalogos] = useState<Catalogos | null>(null);
  const [fase, setFase] = useState<FaseIntervenciones>("cargando");
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  // Ref para decidir si corresponde el esqueleto (sólo la primera carga) sin
  // reiniciar la fase en cada pulso del polling.
  const rowsRef = useRef<Intervencion[] | null>(null);

  const refetch = useCallback(() => setReloadKey((key) => key + 1), []);

  // Recarga inmediata cuando el usuario importa datos desde Excel/CSV.
  useEffect(() => {
    const onRefresh = (): void => refetch();
    window.addEventListener(INTERVENCIONES_REFRESH_EVENT, onRefresh);
    return () => window.removeEventListener(INTERVENCIONES_REFRESH_EVENT, onRefresh);
  }, [refetch]);

  useEffect(() => {
    let cancelled = false;
    let inFlight = false;

    const load = async (): Promise<void> => {
      if (cancelled || inFlight) return;
      // La pestaña oculta no dispara nuevas peticiones (ahorro + foco).
      if (typeof document !== "undefined" && document.hidden) return;
      inFlight = true;
      // Sólo bloquea con skeleton la primera carga; el refresco es silencioso.
      if (rowsRef.current === null) setFase("cargando");
      setError(null);

      try {
        // Ventana mínima que cubre la actual + la de comparación (la derivación
        // ya acota cada serie); sin límite superior.
        const hoy = new Date();
        const diasActuales = DIAS_ACTUALES[rango ?? "24h"] ?? 1;
        const diasComparacion = DIAS_COMPARACION[period ?? "ayer"] ?? 1;
        // Cubre la ventana actual + la previa del período, y al menos el rango.
        const diasFetch = Math.max(diasActuales, diasComparacion * 2);
        const inicio = new Date(hoy);
        inicio.setDate(hoy.getDate() - diasFetch);
        const fechaInicio = isoLocal(inicio);

        // Recolección paginada (PostgREST recorta a 1000 filas por request).
        const unidadFiltro = unidadFiltrable(unidad);
        const filas = await recolectarTodas<Intervencion>(() => {
          let query = supabase.from("intervenciones_diarias").select("*");
          if (unidadFiltro) query = query.eq("jefatura_regional", unidadFiltro);
          query = query.gte("fecha_consulta", fechaInicio);
          return query.order("id", { ascending: true });
        });
        if (cancelled) return;
        rowsRef.current = filas;
        setRows(filas);
        setFase("listo");

        // Catálogo COMPLETO de regionales/dependencias (sin filtro de unidad)
        // para que el selector dinámico no se colapse al filtrar. Es auxiliar:
        // si falla, se conserva el catálogo previo y no se rompe la UI.
        try {
          const catFilas = await recolectarTodas<FilaCatalogo>(() =>
            supabase
              .from("intervenciones_diarias")
              .select("jefatura_regional, dependencia")
              .order("id", { ascending: true }),
          );
          if (cancelled) return;
          setCatalogos({
            regionales: unicosDe(
              catFilas.filter((row) => esJefaturaCatalogada(row.jefatura_regional)),
              (row) => row.jefatura_regional ?? "",
            ),
            dependencias: unicosDe(catFilas, (row) => row.dependencia ?? ""),
          });
        } catch (catCause: unknown) {
          if (cancelled) return;
          console.error(catCause);
        }
      } catch (cause: unknown) {
        if (cancelled) return;
        // Con datos previos se conserva la última lectura real (nunca demo).
        if (rowsRef.current === null) {
          const message = cause instanceof Error ? cause.message : "Error desconocido";
          setRows(null);
          setError(message || "No se pudieron cargar las intervenciones.");
          setFase("error");
        }
      } finally {
        inFlight = false;
      }
    };

    void load();
    const timer = window.setInterval(() => {
      void load();
    }, INTERVENCIONES_POLL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [reloadKey, unidad, rango, period]);

  // Derivación sobre las filas crudas traídas por la consulta. El catálogo
  // completo sobrescribe los selectores para no colapsarlos con el filtro de
  // unidad aplicado.
  const datos = useMemo<IntervencionesDerivadas | null>(() => {
    if (rows === null) return null;
    const derivado = derivarEstadisticas(rows, { unidad, rango, period });
    if (catalogos === null) return derivado;
    return {
      ...derivado,
      regionales_disponibles: catalogos.regionales,
      dependencias_disponibles: catalogos.dependencias,
    };
  }, [rows, catalogos, unidad, rango, period]);

  return { fase, datos, error, refetch };
}
