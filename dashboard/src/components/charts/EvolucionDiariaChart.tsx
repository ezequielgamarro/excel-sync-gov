/**
 * «Evolución Diaria de Incidentes».
 *
 * Grafica la serie REAL de incidentes por día (`{ fecha, total }`):
 * `<XAxis dataKey="fecha" />` (días `DD/MM`) y una única serie
 * `<Bar dataKey="total" />` en azul/cyan, con tooltip oscuro y estados
 * `loading`/`error`/`SIN DATOS`. No hay generadores de datos: sin serie, la UI
 * muestra «SIN DATOS».
 */

import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { IncidenteFecha } from "../../types";
import { formatInteger } from "../../lib/format";
import { Skeleton } from "../Skeletons";

export const EVOLUCION_DIARIA_COLOR = "#4cc2ff";

/** Con más días que este umbral, los números sobre las barras se giran en vertical. */
const UMBRAL_ETIQUETA_VERTICAL = 14;

interface EtiquetaProps {
  x?: number;
  y?: number;
  width?: number;
  value?: number;
  vertical: boolean;
}

/** Número sobre la barra; en vertical cuando hay muchos días para que no se choquen. */
function EtiquetaTotal({
  x = 0,
  y = 0,
  width = 0,
  value = 0,
  vertical,
}: EtiquetaProps): JSX.Element {
  const cx = x + width / 2;
  const texto = formatInteger(Number(value));
  return vertical ? (
    <text
      x={cx}
      y={y - 6}
      fill="var(--text-primary)"
      fontSize={11}
      textAnchor="start"
      transform={`rotate(-90 ${cx} ${y - 6})`}
    >
      {texto}
    </text>
  ) : (
    <text x={cx} y={y - 6} fill="var(--text-primary)" fontSize={12} textAnchor="middle">
      {texto}
    </text>
  );
}

export interface EvolucionDiariaChartProps {
  /** Incidentes por día (`{ fecha: "DD/MM", total }`), orden cronológico. */
  data?: IncidenteFecha[];
  loading?: boolean;
  error?: string | null;
  title?: string;
}

interface TooltipEntry {
  name?: string;
  value?: number;
  color?: string;
}

interface TooltipProps {
  active?: boolean;
  label?: string;
  payload?: TooltipEntry[];
}

function DarkTooltip({ active, label, payload }: TooltipProps): JSX.Element | null {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div
      className="rounded-[10px] border border-border-strong p-3 text-sm"
      style={{
        backgroundColor: "var(--bg-surface-2)",
        color: "var(--text-primary)",
        boxShadow: "0 12px 32px -18px rgba(0,0,0,0.95)",
      }}
    >
      <p className="font-display text-base font-semibold uppercase tracking-wide">{label}</p>
      {payload.map((entry) => (
        <p key={entry.name} className="num mt-1" style={{ color: entry.color }}>
          {entry.name}: {formatInteger(entry.value ?? 0)}
        </p>
      ))}
    </div>
  );
}

export function EvolucionDiariaChart({
  data,
  loading = false,
  error = null,
  title = "Evolución Diaria de Incidentes",
}: EvolucionDiariaChartProps): JSX.Element {
  const rows = (data ?? []).filter((item) => item && String(item.fecha).trim() !== "");
  const vertical = rows.length > UMBRAL_ETIQUETA_VERTICAL;

  return (
    <section className="panel flex h-full min-h-0 flex-col overflow-hidden">
      <h2 className="panel-title panel-title--cap mb-3">{title}</h2>

      {loading && rows.length === 0 ? (
        <div
          className="flex min-h-0 flex-1 flex-col gap-3"
          role="status"
          aria-label={`Cargando ${title}…`}
        >
          <Skeleton className="h-4 w-1/2" />
          <Skeleton className="h-3/4 w-full" />
        </div>
      ) : error && rows.length === 0 ? (
        <p role="alert" className="flex flex-1 items-center justify-center text-sm text-neg">
          No se pudieron cargar los datos. {error}
        </p>
      ) : rows.length === 0 ? (
        <p role="status" className="flex flex-1 items-center justify-center text-sm text-muted">
          SIN DATOS
        </p>
      ) : (
        <div
          className="relative min-h-0 min-w-0 flex-1 overflow-hidden"
          style={{ minHeight: 180 }}
          data-testid="chart-evolucion-diaria"
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={rows} margin={{ top: vertical ? 40 : 24, right: 16, bottom: 8, left: 0 }}>
              <CartesianGrid stroke="var(--border)" strokeDasharray="2 6" vertical={false} />
              <XAxis
                dataKey="fecha"
                stroke="var(--border-strong)"
                tick={{ fill: "var(--text-secondary)", fontSize: 12 }}
                tickLine={false}
                interval="preserveStartEnd"
                minTickGap={8}
              />
              <YAxis
                stroke="var(--border-strong)"
                tick={{ fill: "var(--text-muted)", fontSize: 12 }}
                tickLine={false}
                width={56}
                allowDecimals={false}
              />
              <Tooltip content={<DarkTooltip />} cursor={{ fill: "var(--accent-soft)" }} />
              <Bar
                dataKey="total"
                name="INCIDENTES"
                fill={EVOLUCION_DIARIA_COLOR}
                radius={[4, 4, 0, 0]}
                isAnimationActive={true}
                animationBegin={0}
                animationDuration={1200}
                animationEasing="ease-out"
              >
                <LabelList
                  dataKey="total"
                  content={(props) => (
                    <EtiquetaTotal
                      {...(props as Omit<EtiquetaProps, "vertical">)}
                      vertical={vertical}
                    />
                  )}
                />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}
