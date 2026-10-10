/**
 * Derivador puro de las vistas REACTIVAS: convierte el listado real de
 * intervenciones (Supabase `intervenciones_diarias`) en la MISMA forma interna
 * (`EstadisticasRespuesta`) que ya consumen `DashboardScreen` y
 * `EstadisticasSection`, de modo que los gráficos Recharts no cambian.
 *
 * No hay generadores de datos: con `rows` vacío se devuelven series vacías (la
 * UI muestra «SIN DATOS», nunca demo). La agregación es TOLERANTE: los campos
 * de texto nulos se tratan como `""` y cada fila cuenta como una intervención.
 */

import type { Intervencion } from "../data/api";
import {
  CAUSAS_PERSONA_POSITIVO,
  SUBTIPOS_ARMA,
  SUBTIPOS_VEHICULO,
  esJefaturaCatalogada,
} from "../data/dependencias";
import type {
  EstadisticaItem,
  EstadisticasKpis,
  EstadisticasRespuesta,
  EstadisticasTotales,
  FlujoGranularidad,
  FlujoPunto,
  IncidenteFecha,
  RankingTop5Item,
} from "../types";
import type { ComparisonPeriod } from "./comparison";

/** Proporción de «positivos» usada como respaldo cuando el origen no la trae. */
export const POSITIVOS_POR_DEFECTO = 0.35;

/** Coerción tolerante de textos: `null`/`undefined` → `""`. */
function texto(value: unknown): string {
  return typeof value === "string" ? value : "";
}

/** `true` si `row.tipo_consulta` contiene `fragmento` (sin distinguir mayúsculas). */
function tipoIncluye(row: Intervencion, fragmento: string): boolean {
  return texto(row.tipo_consulta).toLowerCase().includes(fragmento);
}

/**
 * Positivos de una fila: cuenta la fila UNA sola vez (nunca 2), de modo que
 * `positivos <= total` siempre. Devuelve `1` si `resultado_consulta` contiene
 * «positivo»; si no, `0`.
 */
export function positivosDeFila(row: Intervencion): number {
  return texto(row.resultado_consulta).toLowerCase().includes("positivo") ? 1 : 0;
}

/**
 * Total de una intervención: el NUEVO modelo guarda una fila por consulta, por
 * lo que el total es el conteo de filas (cada fila aporta `1`).
 */
export function totalIntervencion(row: Intervencion): number {
  return row ? 1 : 0;
}

/** Acumula `value` por clave textual, preservando el orden de aparición. */
function acumular(
  rows: Intervencion[],
  keyOf: (row: Intervencion) => string,
  valueOf: (row: Intervencion) => number,
): Map<string, number> {
  const mapa = new Map<string, number>();
  for (const row of rows) {
    const key = keyOf(row);
    mapa.set(key, (mapa.get(key) ?? 0) + valueOf(row));
  }
  return mapa;
}

function aItems(mapa: Map<string, number>, ordenarDesc = false): EstadisticaItem[] {
  const items = Array.from(mapa, ([name, value]) => ({ name, value }));
  if (ordenarDesc) {
    items.sort((a, b) => b.value - a.value);
  }
  return items;
}

interface ItemAcumulado {
  value: number;
  positivos: number;
}

/** Acumula `value` y `positivos` por clave textual, preservando el orden. */
function acumularConPositivos(
  rows: Intervencion[],
  keyOf: (row: Intervencion) => string,
  valueOf: (row: Intervencion) => number,
): Map<string, ItemAcumulado> {
  const mapa = new Map<string, ItemAcumulado>();
  for (const row of rows) {
    const key = keyOf(row);
    const acumulado = mapa.get(key) ?? { value: 0, positivos: 0 };
    acumulado.value += valueOf(row);
    acumulado.positivos += positivosDeFila(row);
    mapa.set(key, acumulado);
  }
  return mapa;
}

function aItemsConPositivos(
  mapa: Map<string, ItemAcumulado>,
  ordenarDesc = false,
): EstadisticaItem[] {
  const items = Array.from(mapa, ([name, acumulado]) => ({
    name,
    value: acumulado.value,
    positivos: acumulado.positivos,
  }));
  if (ordenarDesc) {
    items.sort((a, b) => b.value - a.value);
  }
  return items;
}

/** Formatea `YYYY-MM-DD` como `DD/MM`; si no es una fecha ISO, la deja igual. */
function formatoDia(fecha: string): string {
  const partes = fecha.split("-");
  if (partes.length < 3) return fecha;
  const mes = partes[1] ?? "";
  const dia = partes[2] ?? "";
  return `${dia}/${mes}`;
}

/** Claves ordenadas cronológicamente (las ISO comparan como strings). */
function clavesOrdenadas(mapa: Map<string, number>): string[] {
  return Array.from(mapa.keys()).sort((a, b) => a.localeCompare(b));
}

function unicos(rows: Intervencion[], keyOf: (row: Intervencion) => string): string[] {
  const set = new Set<string>();
  for (const row of rows) {
    const key = keyOf(row);
    if (key !== "") set.add(key);
  }
  return Array.from(set).sort((a, b) => a.localeCompare(b));
}

/** Días hacia atrás por rango de filtro (`"24h"` → 1, `"7d"` → 7, `"30d"` → 30). */
const DIAS_POR_RANGO: Readonly<Record<string, number>> = {
  "24h": 1,
  "7d": 7,
  "30d": 30,
};

/** Días de la ventana de comparación inmediatamente anterior a la actual. */
const DIAS_COMPARACION: Readonly<Record<ComparisonPeriod, number>> = {
  ayer: 1,
  semana: 7,
  mes: 30,
  anio: 365,
};

/** Convierte un `Date` a ISO corto `YYYY-MM-DD` (hora local). */
function isoDeFecha(date: Date): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

/** Resta `dias` a una fecha ISO corta `YYYY-MM-DD` y devuelve otra ISO corta. */
function restarDias(iso: string, dias: number): string {
  const partes = iso.split("-");
  const year = Number(partes[0] ?? 0);
  const month = Number(partes[1] ?? 1);
  const day = Number(partes[2] ?? 1);
  const fecha = new Date(year, month - 1, day);
  fecha.setDate(fecha.getDate() - dias);
  return isoDeFecha(fecha);
}

export interface FiltrarIntervencionesOpciones {
  /** Jefatura regional exacta; vacía o `"TODAS"` no filtra. */
  unidad?: string;
  /** Rango de fechas (`"24h"`, `"7d"`, `"30d"`); ausente no filtra por fecha. */
  rango?: string;
  /** Fecha base de «hoy» (por defecto, la actual). */
  hoy?: Date;
}

/**
 * Filtra las filas por Jefatura Regional y rango de fechas ISO cortas.
 *
 * `unidad` vacía o `"TODAS"` no filtra; el rango conserva `[hoy − n, hoy]` y
 * descarta las filas sin `fecha_consulta` (nunca comparables).
 */
export function filtrarIntervenciones(
  rows: Intervencion[],
  opciones: FiltrarIntervencionesOpciones = {},
): Intervencion[] {
  const lista = Array.isArray(rows) ? rows : [];
  const { unidad, rango, hoy } = opciones;
  const filtrarUnidad = unidad !== undefined && unidad !== "" && unidad !== "TODAS";
  const dias = rango !== undefined ? DIAS_POR_RANGO[rango] : undefined;

  let inicioISO: string | null = null;
  let hoyISO: string | null = null;
  if (dias !== undefined) {
    hoyISO = isoDeFecha(hoy ?? new Date());
    inicioISO = restarDias(hoyISO, dias);
  }

  return lista.filter((row) => {
    if (filtrarUnidad && texto(row.jefatura_regional) !== unidad) return false;
    if (dias !== undefined && inicioISO !== null && hoyISO !== null) {
      const fecha = texto(row.fecha_consulta);
      if (fecha === "" || fecha < inicioISO || fecha > hoyISO) return false;
    }
    return true;
  });
}

/**
 * Flujo de consultas, período ACTUAL vs ANTERIOR, por granularidad:
 * - hora: 24 horas del día; actual/anterior = ventana actual/previa del período.
 * - día: últimos 30 días vs los 30 previos.
 * - semana: últimas 12 semanas vs las 12 previas.
 * - mes: últimos 12 meses vs los mismos meses del año anterior.
 * - año: últimos 3 años, cada uno contra el año previo.
 * Todo sale de las filas reales (nada simulado).
 */
function calcularFlujo(
  todas: Intervencion[],
  current: Intervencion[],
  previous: Intervencion[],
  hoyISO: string,
): Record<FlujoGranularidad, FlujoPunto[]> {
  const num = (iso: string): number[] => iso.split("-").map(Number);
  const diaNum = (iso: string): number => {
    const [y, m, d] = num(iso);
    return Math.floor(Date.UTC(y ?? 0, (m ?? 1) - 1, d ?? 1) / 86_400_000);
  };
  const [hy = 0, hm = 1] = num(hoyISO);
  const hoyN = diaNum(hoyISO);

  const porHoraDe = (rows: Intervencion[]): Map<number, number> => {
    const mapa = new Map<number, number>();
    for (const row of rows) {
      const h = Number.parseInt(texto(row.hora_consulta).slice(0, 2), 10);
      if (h >= 0 && h <= 23) mapa.set(h, (mapa.get(h) ?? 0) + 1);
    }
    return mapa;
  };
  const actualHora = porHoraDe(current);
  const anteriorHora = porHoraDe(previous);
  const hora: FlujoPunto[] = Array.from({ length: 24 }, (_, h) => ({
    label: `${String(h).padStart(2, "0")}:00`,
    actual: actualHora.get(h) ?? 0,
    anterior: anteriorHora.get(h) ?? 0,
  }));

  // Cuenta filas por «cubeta» (0 = la actual, 1 = la anterior, …).
  const contar = (cubetaDe: (iso: string) => number): Map<number, number> => {
    const mapa = new Map<number, number>();
    for (const row of todas) {
      const fecha = texto(row.fecha_consulta).slice(0, 10);
      if (!/^\d{4}-\d{2}-\d{2}$/.test(fecha)) continue;
      const b = cubetaDe(fecha);
      if (b >= 0) mapa.set(b, (mapa.get(b) ?? 0) + 1);
    }
    return mapa;
  };
  const serie = (
    conteo: Map<number, number>,
    n: number,
    desfase: number,
    etiqueta: (b: number) => string,
  ): FlujoPunto[] =>
    Array.from({ length: n }, (_, p) => {
      const b = n - 1 - p;
      return {
        label: etiqueta(b),
        actual: conteo.get(b) ?? 0,
        anterior: conteo.get(b + desfase) ?? 0,
      };
    });

  const mesIdx = (y: number, m: number): number => y * 12 + (m - 1);
  const dia = serie(contar((f) => hoyN - diaNum(f)), 30, 30, (b) =>
    formatoDia(restarDias(hoyISO, b)),
  );
  const semana = serie(contar((f) => Math.floor((hoyN - diaNum(f)) / 7)), 12, 12, (b) =>
    `Sem ${formatoDia(restarDias(hoyISO, b * 7))}`,
  );
  const mes = serie(
    contar((f) => {
      const [y = 0, m = 1] = num(f);
      return mesIdx(hy, hm) - mesIdx(y, m);
    }),
    12,
    12,
    (b) => {
      const idx = mesIdx(hy, hm) - b;
      return `${String((idx % 12) + 1).padStart(2, "0")}/${Math.floor(idx / 12)}`;
    },
  );
  const anio = serie(contar((f) => hy - (num(f)[0] ?? 0)), 3, 1, (b) => String(hy - b));

  return { hora, dia, semana, mes, anio };
}

/** Totales reales de un conjunto de intervenciones (tolerante a nulos). */
function calcularTotales(conjunto: Intervencion[]): EstadisticasTotales {
  let positivos = 0;
  let personas = 0;
  let vehiculos = 0;
  let armas = 0;
  let elementos = 0;

  for (const row of conjunto) {
    positivos += positivosDeFila(row);
    if (tipoIncluye(row, "persona")) personas += 1;
    if (tipoIncluye(row, "veh")) vehiculos += 1;
    if (tipoIncluye(row, "arma")) armas += 1;
    if (tipoIncluye(row, "elemento")) elementos += 1;
  }

  return {
    total_intervenciones: conjunto.length,
    total_positivos: positivos,
    consultas_personas: personas,
    consultas_vehiculos: vehiculos,
    consultas_armas: armas,
    consultas_elementos: elementos,
  };
}

/** Fila de la comparativa por Jefatura Regional (actual vs período previo). */
export interface ComparativaRegionalItem {
  name: string;
  mesActual: number;
  mesAnterior: number;
}

/** Punto de la evolución diaria comparada (actual vs período previo alineado). */
export interface ComparativaDiariaItem {
  fecha: string;
  actual: number;
  anterior: number;
}

/** Resultado derivado con totales del período de comparación (si aplica). */
export interface IntervencionesDerivadas extends EstadisticasRespuesta {
  totales_previos?: EstadisticasTotales;
  /** Comparativa por Jefatura Regional: mes actual vs mes anterior. */
  comparativa_regional?: ComparativaRegionalItem[];
  /** Comparativa de evolución diaria: actual vs anterior (alineada por índice). */
  comparativa_diaria?: ComparativaDiariaItem[];
}

export interface DerivarEstadisticasOpciones {
  unidad?: string;
  rango?: string;
  period?: ComparisonPeriod;
  hoy?: Date;
  /** Largo (días) de la ventana actual; tiene prioridad sobre `period`/`rango`. */
  ventanaDias?: number;
}

/** Derivación completa (estado `exito`) a partir de las intervenciones reales. */
export function derivarEstadisticas(
  rows: Intervencion[],
  opciones: DerivarEstadisticasOpciones = {},
): IntervencionesDerivadas {
  // Se descartan filas con jefatura fuera del catálogo (texto suelto, p. ej. «unr»).
  const lista = (Array.isArray(rows) ? rows : []).filter((row) =>
    esJefaturaCatalogada(row.jefatura_regional),
  );
  const { unidad, rango, period, hoy, ventanaDias } = opciones;

  // Ventana de análisis de TODAS las series: el PERÍODO de comparación
  // (`ayer`=1, `semana`=7, `mes`=30, `anio`=365). Si no hay período, cae al
  // rango de la UI (`24h`/`7d`/`30d`). Así barras, tortas, evolución, logística
  // y ranking reaccionan a «Comparar vs», no sólo los totales.
  const diasVentana =
    ventanaDias !== undefined && ventanaDias >= 1
      ? Math.floor(ventanaDias)
      : period !== undefined
        ? (DIAS_COMPARACION[period] ?? DIAS_POR_RANGO[rango ?? "24h"] ?? 1)
        : (DIAS_POR_RANGO[rango ?? "24h"] ?? 1);
  const hoyISO = isoDeFecha(hoy ?? new Date());
  const inicioVentanaISO = restarDias(hoyISO, diasVentana - 1);
  const finPrevioISO = restarDias(inicioVentanaISO, 1);
  const inicioPrevioISO = restarDias(inicioVentanaISO, diasVentana);

  // Filtro base por Jefatura Regional; cada serie acota luego su ventana.
  const soloUnidad = filtrarIntervenciones(lista, { unidad, hoy });
  const enVentana = (row: Intervencion, desde: string, hasta: string): boolean => {
    const fecha = texto(row.fecha_consulta);
    return fecha !== "" && fecha >= desde && fecha <= hasta;
  };

  // Ventana ACTUAL del período: `[hoy − (L − 1), hoy]`.
  const current = soloUnidad.filter((row) => enVentana(row, inicioVentanaISO, hoyISO));
  const totales: EstadisticasTotales = calcularTotales(current);

  // Ventana PREVIA inmediata: `[inicioActual − L, inicioActual − 1 día]`.
  const previous = soloUnidad.filter((row) => enVentana(row, inicioPrevioISO, finPrevioISO));
  const totalesPrevios = calcularTotales(previous);

  // El ranking se calcula sobre la MISMA ventana del período (`current`).
  const rowsRanking = current;
  const porDependenciaRanking = acumularConPositivos(
    rowsRanking,
    (row) => texto(row.dependencia),
    (row) => totalIntervencion(row),
  );

  const kpis: EstadisticasKpis = {
    total_intervenciones: totales.total_intervenciones,
    total_positivos: totales.total_positivos,
    consultas_personas: totales.consultas_personas,
    consultas_vehiculos: totales.consultas_vehiculos,
    consultas_armas: totales.consultas_armas,
  };

  const porFecha = acumular(
    current,
    (row) => texto(row.fecha_consulta),
    (row) => totalIntervencion(row),
  );
  const incidentesPorFecha: IncidenteFecha[] = clavesOrdenadas(porFecha).map((key) => ({
    fecha: formatoDia(key),
    total: porFecha.get(key) ?? 0,
  }));

  const incidentesPorDia: EstadisticaItem[] = clavesOrdenadas(porFecha).map((key) => ({
    name: key,
    value: porFecha.get(key) ?? 0,
  }));

  // Serie HORARIA: agrupa por la hora (`HH`) extraída de `hora_consulta` y
  // devuelve SIEMPRE los 24 buckets (00..23) ordenados, rellenando con 0 los
  // que falten para que el eje no repita etiquetas.
  const porHora = acumular(
    current,
    (row) => texto(row.hora_consulta).slice(0, 2),
    (row) => totalIntervencion(row),
  );
  const incidentesPorHora: EstadisticaItem[] = Array.from({ length: 24 }, (_, hora) => {
    const clave = String(hora).padStart(2, "0");
    return { name: `${clave}:00`, value: porHora.get(clave) ?? 0 };
  });

  const porUnidad = acumularConPositivos(
    current,
    (row) => texto(row.jefatura_regional),
    (row) => totalIntervencion(row),
  );
  const intervencionesPorUnidad = aItemsConPositivos(porUnidad, true);

  const porDependencia = acumularConPositivos(
    current,
    (row) => texto(row.dependencia),
    (row) => totalIntervencion(row),
  );
  const consultasPorDependencia = aItemsConPositivos(porDependencia, true);
  const porDependenciaPrevia = acumular(
    previous,
    (row) => texto(row.dependencia),
    (row) => totalIntervencion(row),
  );
  const porRegionalPrevia = acumular(
    previous,
    (row) => texto(row.jefatura_regional),
    (row) => totalIntervencion(row),
  );
  const porFechaPrevia = acumular(
    previous,
    (row) => texto(row.fecha_consulta),
    (row) => totalIntervencion(row),
  );

  const porTipo = acumular(
    current,
    (row) => texto(row.tipo_consulta),
    (row) => totalIntervencion(row),
  );
  // Todas las categorías de `tipo_consulta` (ya no se filtra por
  // Operativo/Allanamiento); el rescate histórico es innecesario porque no hay
  // filtro que pueda vaciar la serie.
  const distribucionIncidentes = aItems(porTipo);

  const alertasResultados = aItems(
    acumular(
      current,
      (row) => texto(row.sistema_utilizado),
      (row) => totalIntervencion(row),
    ),
    true,
  );

  const vehiculosPorRegional = aItemsConPositivos(
    acumularConPositivos(
      current,
      (row) => texto(row.jefatura_regional),
      (row) => (tipoIncluye(row, "veh") ? 1 : 0),
    ),
    true,
  );

  const armasPorRegional = aItemsConPositivos(
    acumularConPositivos(
      current,
      (row) => texto(row.jefatura_regional),
      (row) => (tipoIncluye(row, "arma") ? 1 : 0),
    ),
    true,
  );

  const aprehendidosPorRegional = aItemsConPositivos(
    acumularConPositivos(
      current,
      (row) => texto(row.jefatura_regional),
      (row) => (tipoIncluye(row, "persona") ? 1 : 0),
    ),
    true,
  );

  // Desgloses por subtipo: se filtran primero las filas del tipo para no generar
  // barras en 0. Sólo cuentan los valores del catálogo cerrado; cualquier otro
  // texto (o vacío) se agrupa como «Sin especificar».
  const desglosar = (
    tipo: string,
    catalogo: readonly string[],
    clave: (row: Intervencion) => string,
  ): EstadisticaItem[] =>
    aItemsConPositivos(
      acumularConPositivos(
        current.filter((row) => tipoIncluye(row, tipo)),
        (row) => (catalogo.includes(clave(row)) ? clave(row) : "Sin especificar"),
        () => 1,
      ),
      true,
    );
  const vehiculosPorTipo = desglosar("veh", SUBTIPOS_VEHICULO, (row) => texto(row.detalle_tipo));
  const armasPorTipo = desglosar("arma", SUBTIPOS_ARMA, (row) => texto(row.detalle_tipo));
  const personasPorCausa = desglosar("persona", CAUSAS_PERSONA_POSITIVO, (row) => texto(row.causas));

  const rankingTop5: RankingTop5Item[] = aItemsConPositivos(porDependenciaRanking)
    .sort((a, b) => b.value - a.value || (b.positivos ?? 0) - (a.positivos ?? 0))
    .slice(0, 10)
    .map((item) => {
      const intervenciones = item.value;
      const previo = porDependenciaPrevia.get(item.name) ?? 0;
      const variacionAbs = intervenciones - previo;
      const variacionPct =
        previo > 0 && Number.isFinite(((intervenciones - previo) / previo) * 100)
          ? ((intervenciones - previo) / previo) * 100
          : null;
      // `positivos` SIEMPRE numérico: si el origen no trae un número finito,
      // se usa un respaldo proporcional. Nunca `undefined` ni string.
      const p = item.positivos;
      const positivosItem =
        typeof p === "number" && Number.isFinite(p)
          ? p
          : Math.floor(intervenciones * 0.3) || 0;
      return {
        name: item.name,
        intervenciones,
        value: intervenciones,
        variacion_abs: variacionAbs,
        variacion_pct: variacionPct,
        positivos: positivosItem,
      };
    });

  const porMes = acumular(
    current,
    (row) => texto(row.fecha_consulta).slice(0, 7),
    (row) => totalIntervencion(row),
  );
  const comparativas: EstadisticaItem[] = clavesOrdenadas(porMes).map((key) => ({
    name: key,
    value: porMes.get(key) ?? 0,
  }));

  // Comparativa por Jefatura Regional: conteo de la ventana ACTUAL vs la PREVIA.
  const comparativaRegional: ComparativaRegionalItem[] = Array.from(
    porUnidad,
    ([name, acumulado]) => ({
      name,
      mesActual: acumulado.value,
      mesAnterior: porRegionalPrevia.get(name) ?? 0,
    }),
  );

  // Comparativa diaria: días de la ventana ACTUAL (orden ascendente) alineados
  // por índice contra los días de la ventana PREVIA (0 si no hay equivalente).
  const clavesActuales = clavesOrdenadas(porFecha);
  const clavesPrevias = clavesOrdenadas(porFechaPrevia);
  const comparativaDiaria: ComparativaDiariaItem[] = clavesActuales.map((key, index) => {
    const clavePrevia = clavesPrevias[index];
    return {
      fecha: formatoDia(key),
      actual: porFecha.get(key) ?? 0,
      anterior: clavePrevia !== undefined ? (porFechaPrevia.get(clavePrevia) ?? 0) : 0,
    };
  });

  return {
    estado: "exito",
    grafico_regionales: intervencionesPorUnidad,
    grafico_dependencias: consultasPorDependencia,
    alertas_resultados: alertasResultados,
    intervenciones_por_unidad: intervencionesPorUnidad,
    consultas_por_dependencia: consultasPorDependencia,
    incidentes_por_fecha: incidentesPorFecha,
    incidentes_por_dia: incidentesPorDia,
    incidentes_por_hora: incidentesPorHora,
    flujo: calcularFlujo(soloUnidad, current, previous, hoyISO),
    distribucion_incidentes: distribucionIncidentes,
    incidentes_por_tipo: distribucionIncidentes,
    logistica_vehiculos_por_regional: vehiculosPorRegional,
    logistica_armas_por_regional: armasPorRegional,
    vehiculosPorRegional,
    armasPorRegional,
    aprehendidosPorRegional,
    vehiculosPorTipo,
    armasPorTipo,
    personasPorCausa,
    comparativas,
    comparativa_regional: comparativaRegional,
    comparativa_diaria: comparativaDiaria,
    kpis,
    totales,
    totales_previos: totalesPrevios,
    rankingTop5,
    regionales_disponibles: unicos(lista, (row) => texto(row.jefatura_regional)),
    dependencias_disponibles: unicos(lista, (row) => texto(row.dependencia)),
  };
}
