/**
 * Importación de intervenciones (Excel/CSV) hacia Supabase.
 *
 * Lee la primera hoja de un `.xlsx`/`.xls`/`.csv` con SheetJS, mapea las
 * cabeceras en español (y las snake_case de la propia tabla, para reimportar lo
 * exportado) a las columnas de `intervenciones_diarias`, limpia/normaliza los
 * valores y hace el alta por lotes reutilizando `normalizarPayloadIntervencion`.
 *
 * Tras importar, el componente que lo invoca emite `INTERVENCIONES_REFRESH_EVENT`
 * para que el dashboard (`useIntervenciones`) y el historial se recarguen.
 */

import * as XLSX from "xlsx";
import { supabase } from "../supabaseClient";
import { normalizarPayloadIntervencion } from "./api";
import type { IntervencionCreate } from "./api";

/** Evento global que fuerza la recarga de las vistas que leen intervenciones. */
export const INTERVENCIONES_REFRESH_EVENT = "intervenciones:refresh";

/** Tamaño de cada lote de inserción. */
const TAMANO_LOTE = 500;

/** Columna destino de una fila importada. */
type ColumnaIntervencion = keyof IntervencionCreate;

/**
 * Mapa cabecera normalizada → columna de la tabla. Incluye variantes en español
 * y las cabeceras snake_case del propio reporte exportado.
 */
const MAPA_CABECERAS: Readonly<Record<string, ColumnaIntervencion>> = {
  "fecha consulta": "fecha_consulta",
  fecha_consulta: "fecha_consulta",
  "hora consulta": "hora_consulta",
  hora_consulta: "hora_consulta",
  jerarquia: "jerarquia",
  "personal policial": "personal_policial",
  personal_policial: "personal_policial",
  "jefatura regional": "jefatura_regional",
  jefatura_regional: "jefatura_regional",
  dependencias: "dependencia",
  dependencia: "dependencia",
  "tipo consulta": "tipo_consulta",
  tipo_consulta: "tipo_consulta",
  identificacion: "identificacion",
  "tipo de arma/vehiculo": "detalle_tipo",
  "detalle del tipo": "detalle_tipo",
  detalle_tipo: "detalle_tipo",
  resultado: "resultado_consulta",
  "resultado consulta": "resultado_consulta",
  resultado_consulta: "resultado_consulta",
  "causas penales": "causas",
  causas: "causas",
  "registro/legajo": "numero_registro",
  "n° de registro": "numero_registro",
  "numero registro": "numero_registro",
  numero_registro: "numero_registro",
  "autoridad judicial": "autoridad_judicial",
  autoridad_judicial: "autoridad_judicial",
  "sistema utilizado": "sistema_utilizado",
  sistema_utilizado: "sistema_utilizado",
  "tramite devuelto": "tramite_devuelto",
  tramite_devuelto: "tramite_devuelto",
  "hora resp": "hora_respuesta",
  "hora respuesta": "hora_respuesta",
  hora_respuesta: "hora_respuesta",
  "personal que informa": "personal_informa",
  personal_informa: "personal_informa",
  cargo: "cargo_informa",
  "cargo del informante": "cargo_informa",
  cargo_informa: "cargo_informa",
  "operativos preventivos": "operativo_preventivo",
  "operativo preventivo": "operativo_preventivo",
  operativo_preventivo: "operativo_preventivo",
  allanamiento: "allanamiento",
  "mini resena": "mini_resena",
  mini_resena: "mini_resena",
  legajo: "legajo",
  "lugar del hecho": "lugar_hecho",
  lugar_hecho: "lugar_hecho",
  "detalle identificacion": "detalle_identificacion",
  detalle_identificacion: "detalle_identificacion",
};

/** Fila con todos los campos por defecto vacíos. */
function filaVacia(): IntervencionCreate {
  return {
    fecha_consulta: "",
    hora_consulta: "",
    jerarquia: "",
    personal_policial: "",
    jefatura_regional: "",
    dependencia: "",
    tipo_consulta: "",
    identificacion: "",
    detalle_tipo: "",
    resultado_consulta: "",
    causas: "",
    numero_registro: "",
    autoridad_judicial: "",
    sistema_utilizado: "",
    tramite_devuelto: "",
    hora_respuesta: "",
    personal_informa: "",
    cargo_informa: "",
    operativo_preventivo: "",
    allanamiento: "",
    mini_resena: "",
  };
}

/** Normaliza una cabecera: `trim`, minúsculas, sin acentos y espacios colapsados. */
export function normalizarCabecera(cabecera: string): string {
  return cabecera
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .trim()
    .toLowerCase()
    .replace(/\s+/g, " ");
}

function dosDigitos(valor: string): string {
  return valor.padStart(2, "0");
}

/**
 * Normaliza una fecha a ISO `YYYY-MM-DD`. Acepta `DD/MM/YYYY`, `DD-MM-YYYY` y
 * `YYYY-MM-DD`. Vacío o inválido → `""` (el saneo posterior lo vuelve `null`).
 */
export function normalizarFecha(valor: unknown): string {
  const texto = String(valor ?? "").trim();
  if (texto === "") return "";

  const iso = texto.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
  if (iso) {
    const [, yyyy, mm, dd] = iso;
    const mes = Number(mm);
    const dia = Number(dd);
    if (mes >= 1 && mes <= 12 && dia >= 1 && dia <= 31) {
      return `${yyyy}-${dosDigitos(mm)}-${dosDigitos(dd)}`;
    }
    return "";
  }

  const local = texto.match(/^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$/);
  if (local) {
    const [, dd, mm, yyyy] = local;
    const mes = Number(mm);
    const dia = Number(dd);
    if (mes >= 1 && mes <= 12 && dia >= 1 && dia <= 31) {
      return `${yyyy}-${dosDigitos(mm)}-${dosDigitos(dd)}`;
    }
    return "";
  }

  return "";
}

/**
 * Normaliza una hora a `HH:MM` cuando matchea (recorta segundos); si no,
 * devuelve el texto tal cual.
 */
export function normalizarHora(valor: unknown): string {
  const texto = String(valor ?? "").trim();
  const match = texto.match(/^(\d{1,2}):(\d{2})(?::\d{2})?$/);
  if (!match) return texto;
  return `${dosDigitos(match[1])}:${match[2]}`;
}

/**
 * Convierte una fila cruda (cabeceras → valores) en un `IntervencionCreate`
 * normalizado. Los campos no reconocidos (`id`, `turno`, …) se descartan.
 * Devuelve `null` si la fila queda totalmente vacía.
 */
export function normalizarFilaImportada(
  raw: Record<string, unknown>,
): IntervencionCreate | null {
  const fila = filaVacia();
  const destino = fila as unknown as Record<string, string>;

  for (const [cabecera, valor] of Object.entries(raw)) {
    const columna = MAPA_CABECERAS[normalizarCabecera(cabecera)];
    if (columna === undefined) continue;
    destino[columna] = String(valor ?? "").trim();
  }

  destino.fecha_consulta = normalizarFecha(destino.fecha_consulta);
  destino.hora_consulta = normalizarHora(destino.hora_consulta);
  destino.hora_respuesta = normalizarHora(destino.hora_respuesta);

  const tieneContenido = Object.values(destino).some((valor) => valor !== "");
  return tieneContenido ? fila : null;
}

/** Normaliza un arreglo de filas crudas, descartando las totalmente vacías. */
export function normalizarFilasImportadas(
  raw: Record<string, unknown>[],
): IntervencionCreate[] {
  const filas: IntervencionCreate[] = [];
  for (const fila of raw) {
    const normalizada = normalizarFilaImportada(fila);
    if (normalizada !== null) filas.push(normalizada);
  }
  return filas;
}

/**
 * Lee la primera hoja de un archivo Excel/CSV y devuelve las filas mapeadas y
 * normalizadas. Usa `raw: false` para obtener los strings tal como se ven.
 */
export async function leerArchivoIntervenciones(file: File): Promise<IntervencionCreate[]> {
  const buffer = await file.arrayBuffer();
  const libro = XLSX.read(new Uint8Array(buffer), { type: "array" });
  const nombreHoja = libro.SheetNames[0];
  if (nombreHoja === undefined) return [];
  const hoja = libro.Sheets[nombreHoja];
  const crudas = XLSX.utils.sheet_to_json<Record<string, unknown>>(hoja, {
    defval: "",
    raw: false,
  });
  return normalizarFilasImportadas(crudas);
}

/**
 * Inserta las filas en `intervenciones_diarias` por lotes de 500, saneando cada
 * una con `normalizarPayloadIntervencion`. Devuelve el total insertado.
 */
export async function importarIntervenciones(filas: IntervencionCreate[]): Promise<number> {
  if (filas.length === 0) return 0;

  let total = 0;
  for (let inicio = 0; inicio < filas.length; inicio += TAMANO_LOTE) {
    const lote = filas.slice(inicio, inicio + TAMANO_LOTE);
    const limpias = lote.map(normalizarPayloadIntervencion);
    const { error } = await supabase.from("intervenciones_diarias").insert(limpias);
    if (error) throw new Error(error.message);
    total += lote.length;
  }
  return total;
}
