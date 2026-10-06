/**
 * Barras horizontales de `grafico_dependencias` (hoja `DASHBOARD_WEB`).
 *
 * Orden descendente por valor y eje Y ancho (160 px, `interval={0}`) para que
 * los nombres largos de dependencias («Comisaría Novena 9°») no se corten ni se
 * solapen. La altura del contenedor es DINÁMICA: `Math.max(n * 40, 600)`.
 * Se descartan las etiquetas vacías.
 */

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

export interface DependenciasBarChartProps {
  data: EstadisticaItem[];
  title?: string;
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

export function DependenciasBarChart({
  data,
  title = "Consultas por Dependencia",
}: DependenciasBarChartProps): JSX.Element {
  const reducedMotion = usePrefersReducedMotion();
  const series = data
    .filter((item) => item.name.trim() !== "")
    .slice()
    .sort((a, b) => b.value - a.value);

  // Altura dinámica: una franja por dependencia (mínimo 600 px legibles).
  const chartHeight = Math.max(series.length * 40, 600);

  return (
    <section className="panel flex h-full min-h-0 flex-col overflow-hidden">
      <h2 className="panel-title panel-title--cap mb-2">{title}</h2>
      <div
        className="relative min-h-0 min-w-0 flex-1 overflow-hidden"
        style={{ minHeight: chartHeight }}
        data-testid="chart-estadisticas-dependencias"
      >
        {series.length === 0 ? (
          <p className="flex h-full items-center justify-center text-sm text-muted" role="status">
            SIN DATOS
          </p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              layout="vertical"
              data={series}
              margin={{ top: 8, right: 56, bottom: 8, left: 8 }}
              accessibilityLayer
            >
              <defs>
                <linearGradient id="estadisticasDependenciasGradient" x1="0" y1="0" x2="1" y2="0">
                  <stop offset="0%" stopColor="#303888" />
                  <stop offset="100%" stopColor="#5161ff" />
                </linearGradient>
              </defs>
              <CartesianGrid horizontal={false} vertical stroke="var(--border)" strokeDasharray="2 6" />
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
                fill="url(#estadisticasDependenciasGradient)"
                radius={[0, 6, 6, 0]}
                isAnimationActive={!reducedMotion}
                animationDuration={400}
                animationEasing="ease-out"
              >
                {series.map((item, index) => (
                  <Cell
                    key={`${item.name}-${index}`}
                    fill="url(#estadisticasDependenciasGradient)"
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
        )}
      </div>
    </section>
  );
}
