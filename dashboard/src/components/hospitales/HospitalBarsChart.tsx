/**
 * Gráfico de barras táctico para el módulo de hospitales.
 *
 * Recibe datos ya agregados (`causa`/`cantidad`) y los dibuja con el mismo
 * tratamiento visual que `TurnosColumnsChart` (gradiente cian, retícula tenue,
 * tooltip oscuro). Maneja el estado vacío dentro del propio panel.
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
import type { HospitalCauseDatum } from "../../types";
import { formatInteger } from "../../lib/format";
import { usePrefersReducedMotion } from "../../hooks/useAnimatedNumber";

export interface HospitalBarsChartProps {
  title: string;
  subtitle?: string;
  data: HospitalCauseDatum[];
  /** Gradiente/identificador único del gráfico (evita colisión de `<defs>`). */
  gradientId: string;
  testId: string;
  /** Alto mínimo del área de dibujo en px. */
  minHeight?: number;
}

interface TooltipProps {
  active?: boolean;
  payload?: Array<{ payload: HospitalCauseDatum }>;
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
      <p className="font-display text-base font-semibold uppercase tracking-wide">{datum.causa}</p>
      <p className="num mt-1">{formatInteger(datum.cantidad)}</p>
    </div>
  );
}

export function HospitalBarsChart({
  title,
  subtitle,
  data,
  gradientId,
  testId,
  minHeight = 220,
}: HospitalBarsChartProps): JSX.Element {
  const reducedMotion = usePrefersReducedMotion();

  return (
    <section className="panel flex h-full min-h-0 flex-col overflow-hidden">
      <h2 className="panel-title panel-title--cap mb-1">{title}</h2>
      {subtitle ? (
        <p className="mb-2 text-[11px] uppercase tracking-wide text-muted">{subtitle}</p>
      ) : null}
      <div
        className="relative min-h-0 min-w-0 flex-1 overflow-hidden"
        style={{ minHeight }}
        data-testid={testId}
      >
        {data.length === 0 ? (
          <p className="flex h-full items-center justify-center text-sm text-muted" role="status">
            SIN DATOS
          </p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data} margin={{ top: 24, right: 16, bottom: 56, left: 0 }}>
              <defs>
                <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#4cc2ff" />
                  <stop offset="100%" stopColor="#1e90ff" />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="var(--border)" strokeDasharray="2 6" vertical={false} />
              <XAxis
                dataKey="causa"
                stroke="var(--border-strong)"
                tick={{ fill: "var(--text-secondary)", fontSize: 12 }}
                tickLine={false}
                interval={0}
                angle={-20}
                textAnchor="end"
                height={70}
              />
              <YAxis
                stroke="var(--border-strong)"
                tick={{ fill: "var(--text-muted)", fontSize: 12 }}
                tickLine={false}
                width={64}
                allowDecimals={false}
              />
              <Tooltip content={<DarkTooltip />} cursor={{ fill: "var(--accent-soft)" }} />
              <Bar
                dataKey="cantidad"
                fill={`url(#${gradientId})`}
                radius={[6, 6, 0, 0]}
                isAnimationActive={!reducedMotion}
                animationDuration={400}
              >
                {data.map((datum) => (
                  <Cell key={datum.causa} fill={`url(#${gradientId})`} fillOpacity={0.9} />
                ))}
                <LabelList
                  dataKey="cantidad"
                  position="top"
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
