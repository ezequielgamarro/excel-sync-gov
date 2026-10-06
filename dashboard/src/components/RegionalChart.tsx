/**
 * VIS-05 — "Intervenciones por Unidad Regional" (RF-03).
 *
 * - Recharts `BarChart layout="vertical"` con 5 categorías en orden canónico.
 * - Eje X `[0, max(datos) × 1,15]`, grid solo vertical, `LabelList right`.
 * - Categoría sin datos → barra 0 + "sin datos" (RF-03.e).
 * - Tabla equivalente accesible y `accessibilityLayer` (teclado).
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
import type { RegionalItem } from "../types";
import { formatPercent, formatSignedInteger, formatSignedPercent } from "../lib/format";
import { buildRegionalBars } from "../lib/barData";
import type { BarFilters } from "../lib/barData";
import type { ComparisonPeriod } from "../lib/comparison";
import { usePrefersReducedMotion } from "../hooks/useAnimatedNumber";

interface RegionalDatum extends RegionalItem {
  sinDatos: boolean;
  highlight: boolean;
  /** `true` cuando no existe base histórica real para el período elegido. */
  sinVariacion: boolean;
}

export interface RegionalChartProps {
  regional: RegionalItem[];
  /** Filtros globales (opcional; por defecto, datos base sin filtrar). */
  filters?: BarFilters;
  /** Período de comparación (opcional). */
  period?: ComparisonPeriod;
  /** Secuencia del snapshot (opcional). */
  seq?: number;
}

function niceStep(domainMax: number): number {
  const rawStep = domainMax / 5;
  const magnitude = Math.pow(10, Math.floor(Math.log10(Math.max(rawStep, 1))));
  const candidates = [1, 2, 2.5, 5, 10].map((multiplier) => multiplier * magnitude);
  const step = candidates.find((candidate) => candidate >= rawStep) ?? 10 * magnitude;
  return Math.max(step, 1);
}

function buildTicks(domainMax: number, minimum = 4): number[] {
  let step = niceStep(domainMax);
  while (domainMax / step < minimum - 1) {
    step = step / 2;
  }
  const ticks: number[] = [];
  for (let tick = 0; tick <= domainMax + 1e-9; tick += step) {
    ticks.push(Math.round(tick * 100) / 100);
  }
  if (ticks[ticks.length - 1] !== domainMax) ticks.push(domainMax);
  return ticks;
}

interface LabelContentProps {
  x?: number;
  y?: number;
  width?: number;
  height?: number;
  value?: number;
  index?: number;
}

function RegionalLabel(props: LabelContentProps & { data: RegionalDatum[] }): JSX.Element | null {
  const { x = 0, y = 0, width = 0, height = 0, value = 0, index = 0, data } = props;
  const datum = data[index];
  const cy = y + height / 2;
  if (datum?.sinDatos) {
    return (
      <text
        x={x + width + 8}
        y={cy}
        fill="var(--text-muted)"
        fontSize={12}
        dominantBaseline="middle"
        fontFamily="'IBM Plex Mono', monospace"
      >
        sin datos
      </text>
    );
  }
  return (
    <text
      x={x + width + 8}
      y={cy}
      fill="var(--text-primary)"
      fontSize={13}
      fontWeight={600}
      dominantBaseline="middle"
      fontFamily="'IBM Plex Mono', monospace"
    >
      {new Intl.NumberFormat("es-CL").format(value)}
    </text>
  );
}

interface TooltipProps {
  active?: boolean;
  payload?: Array<{ payload: RegionalDatum }>;
}

function RegionalTooltip({ active, payload }: TooltipProps): JSX.Element | null {
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
      <p className="font-display text-base font-semibold uppercase tracking-wide">{datum.label}</p>
      <p className="num mt-1">
        Intervenciones: {new Intl.NumberFormat("es-CL").format(datum.intervenciones)}
      </p>
      <p className="num text-ink2">
        Variación:{" "}
        {datum.sinVariacion
          ? "—"
          : `${formatSignedInteger(datum.variacion_abs)} (${formatSignedPercent(datum.variacion_pct)})`}
      </p>
      <p className="num text-ink2">
        Puesto regional: {datum.rank > 0 ? datum.rank : "—"}{" "}
        {datum.sinVariacion ? "" : `(${formatPercent(datum.variacion_pct)})`}
      </p>
    </div>
  );
}

export function RegionalChart({ regional, filters, period }: RegionalChartProps): JSX.Element {
  const reducedMotion = usePrefersReducedMotion();
  const data: RegionalDatum[] = filters
    ? buildRegionalBars(regional, filters, period ?? "ayer").map((bar, index) => ({
        unidad_id: bar.id as RegionalItem["unidad_id"],
        label: bar.label,
        intervenciones: bar.value,
        variacion_abs: bar.deltaAbs ?? 0,
        variacion_pct: bar.deltaPct ?? 0,
        rank: index + 1,
        sinDatos: false,
        highlight: bar.highlight,
        sinVariacion: bar.deltaAbs === null,
      }))
    : regional.map((item) => ({
        ...item,
        sinDatos: item.rank === 0 && item.intervenciones === 0,
        highlight: false,
        sinVariacion: false,
      }));
  const maxValue = data.reduce((max, item) => Math.max(max, item.intervenciones), 0);
  const domainMax = maxValue > 0 ? Math.ceil(maxValue * 1.15) : 5;
  const ticks = buildTicks(domainMax);
  const topValue = maxValue;

  return (
    <section className="panel flex h-full min-h-0 flex-col overflow-hidden">
      <h2 className="panel-title panel-title--cap mb-4">Intervenciones por Unidad Regional</h2>
      <div className="relative min-h-0 min-w-0 flex-1 overflow-hidden" style={{ minHeight: 100 }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            layout="vertical"
            data={data}
            margin={{ top: 8, right: 64, bottom: 8, left: 8 }}
            accessibilityLayer
          >
            <defs>
              <linearGradient id="regionalGradient" x1="0" y1="0" x2="1" y2="0">
                <stop offset="0%" stopColor="#1E90FF" />
                <stop offset="100%" stopColor="#4CC2FF" />
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
              domain={[0, domainMax]}
              ticks={ticks}
              stroke="var(--border-strong)"
              tick={{ fill: "var(--text-muted)", fontSize: 12 }}
              tickLine={false}
            />
            <YAxis
              type="category"
              dataKey="label"
              stroke="var(--border-strong)"
              tick={{ fill: "var(--text-secondary)", fontSize: 13 }}
              width={84}
              tickLine={false}
            />
            <Tooltip content={<RegionalTooltip />} cursor={{ fill: "var(--accent-soft)" }} />
            <Bar
              dataKey="intervenciones"
              fill="url(#regionalGradient)"
              radius={[0, 6, 6, 0]}
              isAnimationActive={!reducedMotion}
              animationDuration={400}
              animationEasing="ease-out"
            >
              {data.map((item) => (
                <Cell
                  key={item.unidad_id}
                  fill={item.highlight ? "#4cc2ff" : "url(#regionalGradient)"}
                  fillOpacity={
                    item.highlight
                      ? 1
                      : item.intervenciones === topValue && topValue > 0
                        ? 0.95
                        : 0.8
                  }
                />
              ))}
              <LabelList
                dataKey="intervenciones"
                position="right"
                content={<RegionalLabel data={data} />}
              />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Tabla equivalente accesible. */}
      <table className="sr-only">
        <caption>Intervenciones por Unidad Regional (tabla de datos)</caption>
        <thead>
          <tr>
            <th scope="col">Unidad Regional</th>
            <th scope="col">Intervenciones</th>
            <th scope="col">Variación</th>
          </tr>
        </thead>
        <tbody>
          {data.map((item) => (
            <tr key={item.unidad_id}>
              <th scope="row">{item.label}</th>
              <td>{item.sinDatos ? "sin datos" : item.intervenciones}</td>
              <td>
                {item.sinDatos || item.sinVariacion
                  ? "—"
                  : `${formatSignedInteger(item.variacion_abs)} (${formatSignedPercent(item.variacion_pct)})`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
