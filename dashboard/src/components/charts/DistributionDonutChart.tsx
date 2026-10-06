import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import type { ConsultaGroup } from "../../types";
import { CHART_PALETTE } from "./filters";
import { Skeleton } from "../Skeletons";

export interface DistributionDonutChartProps {
  title: string;
  /** Agrupación real (Resultado / Causas Penales) de CONSULTAS. */
  groups?: ConsultaGroup[];
  loading?: boolean;
  error?: string | null;
}

interface Slice {
  name: string;
  value: number;
  color: string;
}

interface TooltipProps {
  active?: boolean;
  payload?: Array<{ payload: Slice }>;
}

function DarkTooltip({ active, payload }: TooltipProps): JSX.Element | null {
  if (!active || !payload || payload.length === 0) return null;
  const slice = payload[0].payload;
  return (
    <div
      className="rounded-[10px] border border-border-strong p-3 text-sm"
      style={{
        backgroundColor: "var(--bg-surface-2)",
        color: "var(--text-primary)",
        boxShadow: "0 12px 32px -18px rgba(0,0,0,0.95)",
      }}
    >
      <p className="font-display text-base font-semibold uppercase tracking-wide">{slice.name}</p>
      <p className="num mt-1">{new Intl.NumberFormat("es-CL").format(slice.value)}</p>
    </div>
  );
}

/** Distribución de datos reales (donut) con leyenda lateral ordenada. */
export function DistributionDonutChart({
  title,
  groups,
  loading = false,
  error = null,
}: DistributionDonutChartProps): JSX.Element {
  const raw = (groups ?? []).map((group) => ({ text: group.label, value: group.value }));
  const total = raw.reduce((sum, datum) => sum + datum.value, 0) || 1;
  const slices: Slice[] = [...raw]
    .sort((a, b) => b.value - a.value)
    .map((datum, index) => ({
      name: datum.text,
      value: datum.value,
      color: CHART_PALETTE[index % CHART_PALETTE.length],
    }));

  return (
    <section className="panel flex h-full min-h-0 flex-col overflow-hidden">
      <h2 className="panel-title panel-title--cap mb-1">{title}</h2>

      {loading && slices.length === 0 ? (
        <div className="flex min-h-0 flex-1 flex-col gap-3" role="status" aria-label={`Cargando ${title}…`}>
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="h-3/4 w-full" />
        </div>
      ) : error && slices.length === 0 ? (
        <p role="alert" className="flex flex-1 items-center justify-center text-sm text-neg">
          No se pudo cargar la distribución. {error}
        </p>
      ) : slices.length === 0 ? (
        <p role="status" className="flex flex-1 items-center justify-center text-sm text-muted">
          SIN DATOS
        </p>
      ) : (
        <div className="flex min-h-0 min-w-0 flex-1 flex-col items-center gap-3 lg:flex-row lg:items-stretch lg:gap-4">
          {/*
           * El contenedor de la dona tiene SIEMPRE altura definida:
           * - en móvil (`flex-col`) `flex-1` le da altura en el eje principal;
           * - de `lg` en adelante se estira (`items-stretch`) al alto del panel.
           */}
          <div
            className="relative min-h-[150px] w-full min-w-0 flex-1 overflow-hidden lg:min-h-0"
            data-testid="chart-donut"
          >
            <div className="absolute inset-0">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={slices}
                    dataKey="value"
                    nameKey="name"
                    cx="50%"
                    cy="50%"
                    innerRadius="55%"
                    outerRadius="82%"
                    paddingAngle={2}
                    stroke="none"
                    isAnimationActive={false}
                  >
                    {slices.map((slice) => (
                      <Cell key={slice.name} fill={slice.color} />
                    ))}
                  </Pie>
                  <Tooltip content={<DarkTooltip />} />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/*
           * Leyenda: bajo la dona hasta `lg`; lateral con ancho acotado (`lg:w-56`)
           * en pantallas amplias, para que nunca comprima el ancho de la dona.
           */}
          <ul
            aria-label="Leyenda de distribución"
            className="flex w-full min-w-0 shrink-0 flex-col justify-center gap-1.5 pr-1 text-xs lg:w-56 lg:gap-2"
          >
            {slices.map((slice) => (
              <li key={slice.name} className="flex items-center gap-2 whitespace-nowrap">
                <span
                  aria-hidden="true"
                  className="inline-block h-3 w-3 rounded-sm"
                  style={{ backgroundColor: slice.color }}
                />
                <span className="text-ink2">{slice.name}</span>
                <span className="num ml-auto pl-3 text-muted">
                  {new Intl.NumberFormat("es-CL").format(slice.value)}
                </span>
                <span className="num w-10 text-right text-ink2">
                  {Math.round((slice.value / total) * 100)}%
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
