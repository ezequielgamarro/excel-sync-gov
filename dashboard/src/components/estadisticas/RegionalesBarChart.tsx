/**
 * Barras horizontales de `grafico_regionales` (hoja `DASHBOARD_WEB`).
 *
 * Reutiliza el tratamiento visual de `RegionalChart`: `layout="vertical"`,
 * retícula tenue y tooltip oscuro. El eje Y es ancho (140 px) para que entren
 * los nombres de las unidades regionales y se descartan las etiquetas vacías.
 * Cada barra se apila en dos tramos: «Positivos» (verde) y «Total de
 * Intervenciones» (azul).
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

export interface RegionalesBarChartProps {
  data: EstadisticaItem[];
  title?: string;
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

export function RegionalesBarChart({
  data,
  title = "Intervenciones por Unidad Regional",
}: RegionalesBarChartProps): JSX.Element {
  const series: BarDatumApilado[] = data
    .filter((item) => item.name.trim() !== "")
    .map((item) => {
      const total = Math.max(0, item.value ?? 0);
      const positivos = Math.min(
        total,
        Math.max(0, item.positivos ?? Math.round(total * POSITIVOS_POR_DEFECTO)),
      );
      return { ...item, positivos, resto: Math.max(0, total - positivos) };
    });

  return (
    <section className="panel flex h-full min-h-0 flex-col overflow-hidden">
      <h2 className="panel-title panel-title--cap mb-2">{title}</h2>
      <div
        className="relative min-h-0 min-w-0 flex-1 overflow-hidden"
        style={{ minHeight: 220 }}
        data-testid="chart-estadisticas-regionales"
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
                width={170}
                stroke="var(--border-strong)"
                tick={{ fill: "var(--text-secondary)", fontSize: 13 }}
                tickLine={false}
              />
              <Tooltip content={<DarkTooltip />} cursor={{ fill: "var(--accent-soft)" }} />
              <Legend verticalAlign="top" height={36} />
              <Bar
                dataKey="positivos"
                name="Positivos"
                stackId="a"
                fill="#22c55e"
                maxBarSize={28}
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
                maxBarSize={28}
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
        )}
      </div>
    </section>
  );
}
