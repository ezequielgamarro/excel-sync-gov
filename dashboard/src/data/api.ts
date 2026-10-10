/**
 * Acceso a datos del dashboard 100% Supabase (sin backend propio).
 *
 * - Alta/edición/baja de intervenciones contra la tabla
 *   `intervenciones_diarias` mediante `supabase-js`.
 * - La exportación a Excel se genera en el navegador con SheetJS (XLSX) a
 *   partir de las filas leídas de Supabase.
 */

import * as XLSX from "xlsx";
import { supabase } from "../supabaseClient";

/**
 * Campos de una intervención (tabla `intervenciones_diarias`) en el orden de
 * columnas del reporte exportado.
 */
export const COLUMNAS_REPORTE = [
  "id",
  "fecha_consulta",
  "hora_consulta",
  "jerarquia",
  "personal_policial",
  "jefatura_regional",
  "dependencia",
  "tipo_consulta",
  "identificacion",
  "detalle_tipo",
  "resultado_consulta",
  "causas",
  "numero_registro",
  "autoridad_judicial",
  "sistema_utilizado",
  "tramite_devuelto",
  "hora_respuesta",
  "personal_informa",
  "cargo_informa",
  "operativo_preventivo",
  "allanamiento",
  "mini_resena",
  "legajo",
  "lugar_hecho",
  "detalle_identificacion",
  "created_at",
] as const;

export interface IntervencionCreate {
  fecha_consulta: string | null;
  hora_consulta: string;
  jerarquia: string;
  personal_policial: string;
  jefatura_regional: string;
  dependencia: string;
  tipo_consulta: string;
  identificacion: string;
  detalle_tipo: string;
  resultado_consulta: string;
  causas: string;
  numero_registro: string;
  autoridad_judicial: string;
  sistema_utilizado: string;
  tramite_devuelto: string;
  hora_respuesta: string;
  personal_informa: string;
  cargo_informa: string;
  operativo_preventivo: string;
  allanamiento: string;
  mini_resena: string;
  legajo?: string;
  lugar_hecho?: string;
  /** Texto libre «Tipo / Modelo / Calibre / N° de serie» (`identificacion` es numérica). */
  detalle_identificacion?: string;
}

export interface Intervencion extends IntervencionCreate {
  id: number;
}

/**
 * Campos que en la BD son `bigint`/numéricos aunque el formulario los envíe
 * como texto. Deben convertirse antes de llegar a PostgREST para no enviar un
 * string vacío a una columna `bigint`.
 */
const CAMPOS_NUMERICOS = [
  "identificacion",
  "numero_registro",
  "dni",
  "edad",
  "edad_aparente",
  "cantidad",
] as const;

/**
 * Prepara el payload de una intervención antes de enviarlo a Supabase:
 * - Elimina el `id` (lo autogenera Supabase, es defensivo).
 * - Descarta claves `undefined` (PostgREST no debe recibirlas).
 * - Convierte los campos numéricos a `number`; vacíos/no numéricos → `null`.
 * - Normaliza `fecha_consulta` vacía a `null`.
 */
export function normalizarPayloadIntervencion(
  payload: IntervencionCreate,
): Record<string, unknown> {
  const limpio: Record<string, unknown> = { ...payload };
  delete limpio.id;

  for (const clave of Object.keys(limpio)) {
    if (limpio[clave] === undefined) {
      delete limpio[clave];
    }
  }

  for (const campo of CAMPOS_NUMERICOS) {
    if (!(campo in limpio)) continue;
    const valor = limpio[campo];
    if (valor === null || valor === undefined || valor === "") {
      limpio[campo] = null;
      continue;
    }
    const n = Number(String(valor).trim());
    limpio[campo] = Number.isFinite(n) ? n : null;
  }

  if (limpio.fecha_consulta === "") {
    limpio.fecha_consulta = null;
  }

  return limpio;
}

/** Alta de una intervención (Supabase `intervenciones_diarias`). */
export async function crearIntervencion(payload: IntervencionCreate): Promise<Intervencion> {
  const limpio = normalizarPayloadIntervencion(payload);
  console.log("Payload a Supabase:", limpio);
  const { data, error } = await supabase
    .from("intervenciones_diarias")
    .insert([limpio])
    .select()
    .single();
  if (error) {
    console.error("Error Supabase:", error);
    throw new Error(error.message);
  }
  return data as Intervencion;
}

/** Actualiza por completo una intervención (Supabase `intervenciones_diarias`). */
export async function actualizarIntervencion(
  id: number,
  payload: IntervencionCreate,
): Promise<Intervencion> {
  const limpio = normalizarPayloadIntervencion(payload);
  console.log("Payload a Supabase:", limpio);
  const { data, error } = await supabase
    .from("intervenciones_diarias")
    .update(limpio)
    .eq("id", id)
    .select()
    .single();
  if (error) {
    console.error("Error Supabase:", error);
    throw new Error(error.message);
  }
  return data as Intervencion;
}

/** Elimina una intervención (Supabase `intervenciones_diarias`). */
export async function eliminarIntervencion(id: number): Promise<void> {
  const { error } = await supabase.from("intervenciones_diarias").delete().eq("id", id);
  if (error) throw new Error(error.message);
}

/** Formatea una fecha local como `YYYY-MM-DD` (sin desfase por zona horaria). */
function formatearFechaLocal(date: Date): string {
  const yyyy = date.getFullYear();
  const mm = String(date.getMonth() + 1).padStart(2, "0");
  const dd = String(date.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

/** Traduce el rango de la UI a una ventana de fechas local e inclusiva. */
export function rangoAFechas(rango?: string): { desde?: string; hasta?: string } {
  const dias: Record<string, number> = { "24h": 1, "7d": 6, "30d": 29 };
  const offset = rango ? dias[rango] : undefined;
  if (offset === undefined) return {};
  const hoy = new Date();
  const desde = new Date(hoy);
  desde.setDate(hoy.getDate() - offset);
  return { desde: formatearFechaLocal(desde), hasta: formatearFechaLocal(hoy) };
}

export interface ReportePolicialFiltros {
  /** Nombre EXACTO de la Unidad Regional (`jefatura_regional`); `TODAS` no filtra. */
  unidad?: string;
  /** Rango de la UI (`"24h"`, `"7d"`, `"30d"`). */
  rango?: string;
}

const XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

/** Tamaño de página para la recolección paginada de Supabase (tope de PostgREST). */
export const TAMANO_PAGINA = 1000;

/**
 * Recolecta TODAS las filas de una consulta Supabase paginando con `.range()`.
 *
 * PostgREST limita cada request a `db-max-rows` (1000 por defecto), así que un
 * único `.limit()` no alcanza. `construirConsulta` debe devolver una consulta
 * fresca (con filtros y `.order()` ya aplicados); aquí se itera
 * `[0, 999]`, `[1000, 1999]`, … acumulando los lotes hasta que uno venga
 * incompleto. Lanza si PostgREST reporta error.
 */
export async function recolectarTodas<T>(
  construirConsulta: () => {
    range: (
      desde: number,
      hasta: number,
    ) => PromiseLike<{ data: T[] | null; error: { message: string } | null }>;
  },
): Promise<T[]> {
  const filas: T[] = [];
  for (let desde = 0; ; desde += TAMANO_PAGINA) {
    const { data, error } = await construirConsulta().range(
      desde,
      desde + TAMANO_PAGINA - 1,
    );
    if (error) throw new Error(error.message);
    const lote = data ?? [];
    filas.push(...lote);
    if (lote.length < TAMANO_PAGINA) break;
  }
  return filas;
}

/**
 * Genera el `.xlsx` del reporte policial **filtrado** en el navegador con
 * SheetJS, leyendo las filas directamente de Supabase
 * (`intervenciones_diarias`). Sin backend propio.
 *
 * La unidad llega como valor EXACTO de `charts.regionales_disponibles`
 * (p. ej. "Unidad Regional Norte"), por eso se compara con `.eq` directo.
 */
export async function descargarReportePolicial(
  filtros: ReportePolicialFiltros = {},
): Promise<Blob> {
  const unidad = filtros.unidad?.trim();
  const { desde, hasta } = rangoAFechas(filtros.rango);

  // Paginación obligatoria: PostgREST recorta cada request a 1000 filas.
  const filas = await recolectarTodas<Intervencion>(() => {
    let query = supabase.from("intervenciones_diarias").select("*");
    if (unidad && unidad.toUpperCase() !== "TODAS") {
      query = query.eq("jefatura_regional", unidad);
    }
    if (desde) query = query.gte("fecha_consulta", desde);
    if (hasta) query = query.lte("fecha_consulta", hasta);
    return query.order("id", { ascending: true });
  });

  // Conserva el orden de la hoja: fecha_consulta descendente.
  filas.sort((a, b) => {
    const fa = a.fecha_consulta ?? "";
    const fb = b.fecha_consulta ?? "";
    if (fa < fb) return 1;
    if (fa > fb) return -1;
    return 0;
  });

  const hoja = XLSX.utils.json_to_sheet(filas, { header: [...COLUMNAS_REPORTE] });
  const libro = XLSX.utils.book_new();
  XLSX.utils.book_append_sheet(libro, hoja, "Intervenciones");
  const salida = XLSX.write(libro, { bookType: "xlsx", type: "array" });
  return new Blob([salida], { type: XLSX_MIME });
}
