export interface PositivosLabelProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  value?: number | string;
}

/** Tamaño máximo/mínimo (px) de los números dentro y sobre las barras. */
const FUENTE_MAX = 14;
const FUENTE_MIN = 8;
/** Ancho aproximado de un carácter respecto del tamaño de fuente. */
const ANCHO_CARACTER = 0.62;

/**
 * Número centrado dentro de la barra. El tamaño se ajusta al alto y ancho
 * disponibles para que nunca sea más grande que la barra; si no entra, se omite
 * (el valor sigue disponible en el tooltip).
 */
export function renderPositivosLabel(props: PositivosLabelProps): JSX.Element | null {
  const { x = 0, y = 0, width = 0, height = 0, value } = props;
  if (!value || value === 0 || value === "0") return null;
  const texto = String(value);
  const fontSize = Math.min(
    FUENTE_MAX,
    height - 4,
    width / (texto.length * ANCHO_CARACTER),
  );
  if (fontSize < FUENTE_MIN) return null;
  return (
    <text
      x={x + width / 2}
      y={y + height / 2}
      fill="#ffffff"
      fontWeight="bold"
      fontSize={fontSize}
      textAnchor="middle"
      dominantBaseline="middle"
    >
      {texto}
    </text>
  );
}

export interface TotalLabelProps {
  x?: number;
  y?: number;
  width?: number;
  value?: number | string;
}

/**
 * Total sobre la barra. Se achica para caber en el ancho de la barra y, si aun
 * así no entra, se gira en vertical para que no se pise con las vecinas.
 */
export function renderTotalLabel(props: TotalLabelProps): JSX.Element | null {
  const { x = 0, y = 0, width = 0, value } = props;
  if (value === undefined || value === null || value === "") return null;
  const texto = Number(value).toLocaleString("es-CL");
  const cx = x + width / 2;
  const entra = width / (texto.length * ANCHO_CARACTER);
  if (entra >= FUENTE_MIN) {
    return (
      <text
        x={cx}
        y={y - 6}
        fill="var(--text-primary)"
        fontSize={Math.min(FUENTE_MAX, entra)}
        textAnchor="middle"
      >
        {texto}
      </text>
    );
  }
  return (
    <text
      x={cx}
      y={y - 6}
      fill="var(--text-primary)"
      fontSize={Math.max(FUENTE_MIN, Math.min(FUENTE_MAX, width - 2))}
      textAnchor="start"
      transform={`rotate(-90 ${cx} ${y - 6})`}
    >
      {texto}
    </text>
  );
}

export interface TickInclinadoProps {
  x?: number;
  y?: number;
  payload?: { value?: string | number };
}

const TICK_MAX_CARACTERES = 18;

/**
 * Etiqueta del eje X girada a -40° y recortada: los nombres largos (p. ej.
 * «Departamento de Inteligencia Criminal») no se pisan entre sí. El nombre
 * completo queda en el `<title>` (hover) y en el tooltip del gráfico.
 */
export function TickInclinado({ x = 0, y = 0, payload }: TickInclinadoProps): JSX.Element {
  const completo = String(payload?.value ?? "");
  const texto =
    completo.length > TICK_MAX_CARACTERES
      ? `${completo.slice(0, TICK_MAX_CARACTERES - 1)}…`
      : completo;
  return (
    <g transform={`translate(${x},${y})`}>
      <title>{completo}</title>
      <text
        x={0}
        y={0}
        dy={10}
        fill="var(--text-secondary)"
        fontSize={11}
        textAnchor="end"
        transform="rotate(-40)"
      >
        {texto}
      </text>
    </g>
  );
}
