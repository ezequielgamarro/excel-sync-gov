/**
 * Barras HORIZONTALES reutilizables (`layout="vertical"`) para series reales
 * `{ name, value }` (p. ej. vehículos/armas secuestrados por Unidad Regional).
 *
 * Altura DINÁMICA: `Math.max(n * 40, 320)`; eje Y de categorías de 160 px con
 * `interval={0}` para que los nombres largos («Unidad Regional ...») no se
 * corten. Paleta azul/cyan, tooltip oscuro y estados `loading`/`error`/`SIN
 * DATOS`. Sin datos ⇒ «SIN DATOS», nunca demo.
 */

import { useId } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { EstadisticaItem } from "../../types";
import { formatInteger } from "../../lib/format";
import { usePrefersReducedMotion } from "../../hooks/useAnimatedNumber";
import { Skeleton } from "../Skeletons";

/** Altura mínima legible de las barras horizontales. */
export const HORIZONTAL_MIN_HEIGHT = 320;

export interface BarrasHorizontalesChartProps {
  /** Serie real `[{ name, value }]`. */
  data?: EstadisticaItem[];
  title: string;
  /** `data-testid` del contenedor del gráfico (cuando hay datos). */
  testId?: string;
  loading?: boolean;
  error?: string | null;
}

interface TooltipProps {
  active?: boolean;
  payload?: Array<{ payload: EstadisticaItem }>;
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
  const reducedMotion = usePrefersReducedMotion();
  const gradientId = `barrasHorizontales${useId().replace(/:/g, "")}`;
  const series = (data ?? [])
    .filter((item) => item.name.trim() !== "")
    .slice()
    .sort((a, b) => b.value - a.value);

  // Altura dinámica: una franja por etiqueta (mínimo 320 px legibles).
  const chartHeight = Math.max(series.length * 40, HORIZONTAL_MIN_HEIGHT);

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
        <div
          className="relative min-w-0 overflow-hidden"
          style={{ height: chartHeight }}
          data-testid={testId ?? "chart-barras-horizontales"}
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              layout="vertical"
              data={series}
              margin={{ top: 8, right: 56, bottom: 8, left: 8 }}
              accessibilityLayer
            >
              <defs>
                <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stopColor="#4cc2ff" />
                  <stop offset="100%" stopColor="#1e90ff" />
                </linearGradient>
              </defs>
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
                width={160}
                interval={0}
                stroke="var(--border-strong)"
                tick={{ fill: "var(--text-secondary)", fontSize: 13 }}
                tickLine={false}
              />
              <Tooltip content={<DarkTooltip />} cursor={{ fill: "var(--accent-soft)" }} />
              <Bar
                dataKey="value"
                fill={`url(#${gradientId})`}
                radius={[0, 6, 6, 0]}
                isAnimationActive={!reducedMotion}
                animationDuration={400}
                animationEasing="ease-out"
              >
                {series.map((item, index) => (
                  <Cell
                    key={`${item.name}-${index}`}
                    fill={`url(#${gradientId})`}
                    fillOpacity={0.9}
                  />
                ))}
                <LabelList
                  dataKey="value"
                  position="right"
                  formatter={(value: number) => formatInteger(value)}
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
