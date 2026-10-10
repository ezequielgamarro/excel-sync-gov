/**
 * Catálogo estático de Unidades Regionales y sus dependencias (comisarías) de
 * la Policía de Tucumán. Alimenta la cascada ESTRICTA Regional → Dependencia del
 * formulario táctico de carga de intervenciones: cada regional expone únicamente
 * sus propias dependencias y, al cambiar de jefatura, la dependencia elegida se
 * resetea.
 *
 * Las jefaturas usan el formato abreviado «U.R. X». Los nombres de dependencia
 * fueron reconciliados con los guardados en Supabase
 * (`public.intervenciones_diarias`): donde el nombre pedido era una variante
 * ligera de un valor REAL ya presente en el seed se usa el valor real
 * (p. ej. «Comisaría Yerba Buena» → «Cria. Yerba Buena», «Comisaría Tafí Viejo
 * Centro» → «Cria. Tafí Viejo», «Comisaría Seccional N» → «Comisaría N»); donde
 * el nombre no existe en el seed se deja el nombre nuevo tal cual.
 */

export type Dependencia = string;

export const UNIDADES_REGIONALES = [
  "U.R. Capital",
  "U.R. Norte",
  "U.R. Sur",
  "U.R. Este",
  "U.R. Oeste",
] as const;

export type UnidadRegional = (typeof UNIDADES_REGIONALES)[number];

/** Dependencias de «U.R. Capital» (comisarías numeradas reales del seed). */
const CAPITAL: readonly Dependencia[] = [
  "Comisaría 1",
  "Comisaría 2",
  "Comisaría 3",
  "Comisaría 4",
  "Comisaría 5",
  "Comisaría 6",
  "Comisaría 7",
  "Comisaría 8",
  "Comisaría 9",
  "Comisaría 10",
  "Comisaría 11",
  "Comisaría 12",
  "Comisaría 13",
  "Comisaría 14",
  "Comisaría 15",
];

/** Dependencias de «U.R. Norte». */
const NORTE: readonly Dependencia[] = [
  "Cria. Yerba Buena",
  "Cria. Marti Coll",
  "Comisaría Cevil Redondo",
  "Comisaría El Corte",
  "Cria. Tafí Viejo",
  "Cria. Lomas de Tafí",
  "Comisaría Villa Obrera",
  "Comisaría El Colmenar",
  "Comisaría Los Pocitos",
  "Cria. Trancas",
  "Cria. Villa Mariano Moreno",
];

/** Dependencias de «U.R. Este». */
const ESTE: readonly Dependencia[] = [
  "Cria. Banda del Río Salí",
  "Comisaría Lastenia",
  "Cria. Alderetes",
  "Comisaría San Andrés",
  "Comisaría Delfín Gallo",
  "Cria. Bella Vista",
];

/** Dependencias de «U.R. Sur». */
const SUR: readonly Dependencia[] = [
  "Cria. Concepción",
  "Cria. Aguilares",
  "Cria. Alberdi",
  "Cria. La Cocha",
  "Comisaría Graneros",
];

/** Dependencias de «U.R. Oeste». */
const OESTE: readonly Dependencia[] = [
  "Cria. Tafí del Valle",
  "Cria. Famaillá",
  "Cria. Monteros",
  "Cria. Lules",
  "Comisaría Acheral",
  "Cria. El Manantial",
];

/** Unión deduplicada de todas las dependencias (compatibilidad). */
export const DEPENDENCIAS: readonly Dependencia[] = [
  ...new Set([...CAPITAL, ...NORTE, ...ESTE, ...SUR, ...OESTE]),
];

export const DEPENDENCIAS_POR_REGIONAL: Record<UnidadRegional, readonly Dependencia[]> = {
  "U.R. Capital": CAPITAL,
  "U.R. Norte": NORTE,
  "U.R. Sur": SUR,
  "U.R. Este": ESTE,
  "U.R. Oeste": OESTE,
};

/**
 * Direcciones: nivel organizativo hermano de las Unidades Regionales. No tienen
 * divisiones/dependencias propias, así que se guardan en `jefatura_regional` y
 * `dependencia` queda vacía.
 */
export const DIRECCIONES = [
  "D.G.I.C.Y.D.C",
  "Delitos Rural y Ambientales",
  "DI.GE.DROP",
  "Departamento de Inteligencia Criminal",
  "D.G.U.E",
  "D.G. Policía Vial",
  "D.G.T.P.Y.V.G",
] as const;

export type Direccion = (typeof DIRECCIONES)[number];

export function esDireccion(nombre: string): boolean {
  return (DIRECCIONES as readonly string[]).includes(nombre);
}

/**
 * `true` si la jefatura es vacía, una Unidad Regional o una Dirección. Los textos
 * sueltos fuera del catálogo (p. ej. «unr») no deben aparecer en gráficos ni filtros.
 */
export function esJefaturaCatalogada(nombre: string | null | undefined): boolean {
  const limpio = (nombre ?? "").trim();
  return (
    limpio === "" ||
    (UNIDADES_REGIONALES as readonly string[]).includes(limpio) ||
    esDireccion(limpio)
  );
}

/** Jerarquías de la Policía de la Provincia de Tucumán (de mayor a menor). */
export const JERARQUIAS = [
  "Jefe de Policía",
  "Subjefe de Policía",
  "Comisario General",
  "Comisario Mayor",
  "Comisario Inspector",
  "Comisario",
  "Subcomisario",
  "Oficial Principal",
  "Oficial Inspector",
  "Oficial Subinspector",
  "Oficial Ayudante",
  "Suboficial Mayor",
  "Suboficial Principal",
  "Sargento Ayudante",
  "Sargento Primero",
  "Sargento",
  "Cabo Primero",
  "Cabo",
  "Agente",
  "Personal Civil",
] as const;

/** Subtipos de vehículo y de arma (catálogo cerrado del formulario). */
export const SUBTIPOS_VEHICULO = ["Auto", "Moto", "Camioneta", "Trafic", "Otros"] as const;
export const SUBTIPOS_ARMA = [
  "Pistola",
  "Revólver",
  "Escopeta",
  "Fusil",
  "Arma de repartición",
  "Otros",
] as const;

/** Causas posibles cuando la consulta es Persona con resultado Positivo. */
export const CAUSAS_PERSONA_POSITIVO = [
  "Causa penal / flagrancia",
  "Pedido de captura / detención",
  "Prohibición de salida de la provincia / país",
  "Paradero por comparendo",
  "Medidas restrictivas",
  "Medidas restrictivas vinculadas a familia y género",
] as const;
