/**
 * Barras HORIZONTALES reutilizables (`layout="vertical"`) para series reales
 * `{ name, value }` (p. ej. vehículos/armas secuestrados por Unidad Regional).
 *
 * Altura DINÁMICA: `Math.max(300, n * 45)` y crece libremente (sin scroll
 * interno); eje Y de categorías de 150 px con `interval={0}` para
 * que los nombres largos («Unidad Regional ...») no se corten. Cada barra se
 * apila en dos tramos: «Positivos» (verde) y «Total de Intervenciones» (azul). Sin
 * datos ⇒ «SIN DATOS», nunca demo.
 */

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
import type { EstadisticaItem } from "../../types";
import { formatInteger } from "../../lib/format";
import { POSITIVOS_POR_DEFECTO } from "../../lib/intervenciones";
import { renderPositivosLabel } from "../../lib/rechartsLabels";
import type { PositivosLabelProps } from "../../lib/rechartsLabels";
import { Skeleton } from "../Skeletons";

export interface BarrasHorizontalesChartProps {
  /** Serie real `[{ name, value }]`. */
  data?: EstadisticaItem[];
  title: string;
  /** `data-testid` del contenedor del gráfico (cuando hay datos). */
  testId?: string;
  loading?: boolean;
  error?: string | null;
}

interface BarDatumApilado extends EstadisticaItem {
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
  return (
    <div
      className="rounded-[10px] border border-border-strong p-3 text-sm"
      style={{
        backgroundColor: "var(--bg-surface-2)",
        color: "var(--text-primary)",
        boxShadow: "0 12px 32px -18px rgba(0,0,0,0.95)",
      }}
    >
      <p className="font-display text-base font-semibold uppercase tracking-wide">{datum.name}</p>
      <p className="num mt-1">{formatInteger(datum.value)}</p>
      <p className="num text-xs text-emerald-400">Positivos: {formatInteger(datum.positivos)}</p>
      <p className="num text-xs text-muted">Resto: {formatInteger(datum.resto)}</p>
    </div>
  );
}

export function BarrasHorizontalesChart({
  data,
  title,
  testId,
  loading = false,
  error = null,
}: BarrasHorizontalesChartProps): JSX.Element {
  const series: BarDatumApilado[] = (data ?? [])
    .filter((item) => item.name.trim() !== "")
    .slice()
    .sort((a, b) => b.value - a.value)
    .map((item) => {
      const total = Math.max(0, item.value ?? 0);
      const positivos = Math.min(
        total,
        Math.max(0, item.positivos ?? Math.round(total * POSITIVOS_POR_DEFECTO)),
      );
      return { ...item, positivos, resto: Math.max(0, total - positivos) };
    });

  // Altura dinámica: una franja por etiqueta (mínimo 300 px legibles).
  const chartHeight = Math.max(300, series.length * 45);

  return (
    <section className="panel flex flex-col">
      <h2 className="panel-title panel-title--cap mb-2">{title}</h2>

      {loading && series.length === 0 ? (
        <div
          className="flex flex-col gap-3"
          style={{ minHeight: chartHeight }}
          role="status"
          aria-label={`Cargando ${title}…`}
        >
          <Skeleton className="h-4 w-1/2" />
          <Skeleton className="h-3/4 w-full" />
        </div>
      ) : error && series.length === 0 ? (
        <p
          role="alert"
          className="flex items-center justify-center text-sm text-neg"
          style={{ minHeight: chartHeight }}
        >
          No se pudieron cargar los datos. {error}
        </p>
      ) : series.length === 0 ? (
        <p
          role="status"
          className="flex items-center justify-center text-sm text-muted"
          style={{ minHeight: chartHeight }}
        >
          SIN DATOS
        </p>
      ) : (
        <div className="min-w-0" data-testid={testId ?? "chart-barras-horizontales"}>
          <ResponsiveContainer width="100%" height={chartHeight}>
            <BarChart
              layout="vertical"
              data={series}
              margin={{ top: 8, right: 56, bottom: 8, left: 8 }}
              accessibilityLayer
            >
              <CartesianGrid
                horizontal={false}
                vertical
                stroke="var(--border)"
                strokeDasharray="2 6"
              />
              <XAxis
                type="number"
                allowDecimals={false}
                stroke="var(--border-strong)"
                tick={{ fill: "var(--text-muted)", fontSize: 12 }}
                tickLine={false}
              />
              <YAxis
                type="category"
                dataKey="name"
                width={150}
                interval={0}
                stroke="var(--border-strong)"
                tick={{ fill: "var(--text-secondary)", fontSize: 12 }}
                tickLine={false}
              />
              <Tooltip content={<DarkTooltip />} cursor={{ fill: "var(--accent-soft)" }} />
              <Legend verticalAlign="top" height={36} />
              <Bar
                dataKey="positivos"
                name="Positivos"
                stackId="a"
                fill="#22c55e"
                maxBarSize={40}
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
                radius={[0, 6, 6, 0]}
                maxBarSize={40}
                isAnimationActive={true}
                animationBegin={0}
                animationDuration={1200}
                animationEasing="ease-out"
              >
                <LabelList
                  dataKey="value"
                  position="right"
                  formatter={(value: number) => value.toLocaleString("es-CL")}
                  style={{ fill: "var(--text-primary)", fontSize: 12 }}
                />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}
