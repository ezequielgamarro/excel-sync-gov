import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { ConsultaGroup } from "../../types";
import { buildGroupBars } from "../../lib/barData";
import type { BarDatum } from "../../lib/barData";
import { POSITIVOS_POR_DEFECTO } from "../../lib/intervenciones";
import { renderPositivosLabel, renderTotalLabel, TickInclinado } from "../../lib/rechartsLabels";
import type { PositivosLabelProps, TotalLabelProps } from "../../lib/rechartsLabels";
import { Skeleton } from "../Skeletons";

export interface ColumnsChartProps {
  title: string;
  testId: string;
  /** Agrupación real de CONSULTAS (Jefatura Regional / Turno). */
  groups?: ConsultaGroup[];
  loading?: boolean;
  error?: string | null;
  /** Identificador de gradiente (unidad/turno). */
  mode?: "unidad" | "turno";
}

interface BarDatumApilado extends BarDatum {
  positivos: number;
  resto: number;
}

interface TooltipProps {
  active?: boolean;
  payload?: Array<{ payload: BarDatumApilado }>;
}

function DarkTooltip({ active, payload }: TooltipProps): JSX.Element | null {
  if (!active || !payload || payload.length === 0) return null;
  const datum = payload[0].payload;
  const pct = datum.deltaPct;
  const arrow = datum.direction === "up" ? "▲" : datum.direction === "down" ? "▼" : "·";
  return (
    <div
      className="rounded-[10px] border border-border-strong p-3 text-sm"
      style={{
        backgroundColor: "var(--bg-surface-2)",
        color: "var(--text-primary)",
        boxShadow: "0 12px 32px -18px rgba(0,0,0,0.95)",
      }}
    >
      <p className="font-display text-base font-semibold uppercase tracking-wide">{datum.label}</p>
      <p className="num mt-1">{new Intl.NumberFormat("es-CL").format(datum.value)}</p>
      <p className="num text-xs text-emerald-400">Positivos: {datum.positivos}</p>
      <p className="num text-xs text-muted">Resto: {datum.resto}</p>
      <p className="num text-xs text-muted">
        {datum.baseline === null || pct === null
          ? "sin histórico"
          : `vs período anterior: ${new Intl.NumberFormat("es-CL").format(datum.baseline)} ${arrow} ${
              pct > 0 ? "+" : ""
            }${pct.toFixed(1)} %`}
      </p>
    </div>
  );
}

/** Columnas reales por unidad regional o por turno operativo (CONSULTAS). */
export function TurnosColumnsChart({
  title,
  testId,
  groups,
  loading = false,
  error = null,
}: ColumnsChartProps): JSX.Element {
  const data: BarDatumApilado[] = buildGroupBars(groups ?? []).map((datum) => {
    const total = Math.max(0, datum.value ?? 0);
    const item = datum as BarDatum & { positivos?: number };
    const positivos = Math.min(
      total,
      Math.max(0, item.positivos ?? Math.round(total * POSITIVOS_POR_DEFECTO)),
    );
    return { ...datum, positivos, resto: Math.max(0, total - positivos) };
  });

  return (
    <section className="panel flex h-full min-h-0 flex-col overflow-hidden">
      <h2 className="panel-title panel-title--cap mb-3">{title}</h2>

      {loading && data.length === 0 ? (
        <div
          className="flex min-h-0 flex-1 flex-col gap-3"
          role="status"
          aria-label={`Cargando ${title}…`}
        >
          <Skeleton className="h-4 w-1/2" />
          <Skeleton className="h-3/4 w-full" />
        </div>
      ) : error && data.length === 0 ? (
        <p role="alert" className="flex flex-1 items-center justify-center text-sm text-neg">
          No se pudieron cargar los datos. {error}
        </p>
      ) : data.length === 0 ? (
        <p role="status" className="flex flex-1 items-center justify-center text-sm text-muted">
          SIN DATOS
        </p>
      ) : (
        <div
          className="relative min-h-0 min-w-0 flex-1 overflow-hidden"
          style={{ minHeight: 180 }}
          data-testid={testId}
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={data}
              barCategoryGap="15%"
              margin={{ top: 40, right: 16, bottom: 8, left: 0 }}
            >
              <CartesianGrid stroke="var(--border)" strokeDasharray="2 6" vertical={false} />
              <XAxis
                dataKey="label"
                stroke="var(--border-strong)"
                tick={<TickInclinado />}
                tickLine={false}
                interval={0}
                height={78}
              />
              <YAxis
                stroke="var(--border-strong)"
                tick={{ fill: "var(--text-muted)", fontSize: 12 }}
                tickLine={false}
                width={64}
              />
              <Tooltip content={<DarkTooltip />} cursor={{ fill: "var(--accent-soft)" }} />
              <Legend verticalAlign="top" height={36} />
              <Bar
                dataKey="positivos"
                name="Positivos"
                stackId="a"
                fill="#22c55e"
                isAnimationActive={true}
                animationBegin={0}
                animationDuration={1200}
                animationEasing="ease-out"
              >
                <LabelList
                  dataKey="positivos"
                  content={(props) => renderPositivosLabel(props as PositivosLabelProps)}
                />
              </Bar>
              <Bar
                dataKey="resto"
                name="Total de Intervenciones"
                stackId="a"
                fill="#3b82f6"
                radius={[6, 6, 0, 0]}
                isAnimationActive={true}
                animationBegin={0}
                animationDuration={1200}
                animationEasing="ease-out"
              >
                <LabelList
                  dataKey="value"
                  content={(props) => renderTotalLabel(props as TotalLabelProps)}
                />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}
