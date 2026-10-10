/**
 * «Flujo de Consultas».
 *
 * Líneas animadas que comparan el período ACTUAL contra el ANTERIOR, con
 * selector de granularidad: Hora, Día, Semana, Mes y Año. Todos los valores salen
 * de las intervenciones reales (nada simulado); al cambiar de granularidad o de
 * datos las líneas se vuelven a dibujar con animación.
 */

import { useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { FlujoGranularidad, FlujoPunto } from "../../types";
import { formatInteger } from "../../lib/format";
import { Skeleton } from "../Skeletons";

const GRANULARIDADES: ReadonlyArray<{
  id: FlujoGranularidad;
  etiqueta: string;
  descripcion: string;
}> = [
  { id: "hora", etiqueta: "Hora", descripcion: "Consultas por hora del día, período seleccionado vs anterior" },
  { id: "dia", etiqueta: "Día", descripcion: "Últimos 30 días vs los 30 días previos" },
  { id: "semana", etiqueta: "Semana", descripcion: "Últimas 12 semanas vs las 12 previas" },
  { id: "mes", etiqueta: "Mes", descripcion: "Últimos 12 meses vs los mismos meses del año anterior" },
  { id: "anio", etiqueta: "Año", descripcion: "Últimos 3 años, cada uno contra el año previo" },
];

const COLOR_ACTUAL = "#3b82f6";
const COLOR_ANTERIOR = "#f59e0b";

/** Serie horaria simple `{ ts, value }` → puntos (sin período anterior). */
function desdeSerie(series?: Array<{ ts: string; value: number }>): FlujoPunto[] {
  return (series ?? [])
    .filter((point) => point.ts !== "" && Number.isFinite(point.value))
    .map((point) => ({ label: point.ts, actual: point.value, anterior: 0 }))
    .sort((a, b) => a.label.localeCompare(b.label));
}

const sumar = (puntos: FlujoPunto[], campo: "actual" | "anterior"): number =>
  puntos.reduce((acc, punto) => acc + punto[campo], 0);

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
      <p className="num text-xs text-muted">{typeof label === "string" ? label : ""}</p>
      {payload.map((entry) => (
        <p key={entry.name} className="num mt-1" style={{ color: entry.color }}>
          {entry.name}: {formatInteger(entry.value ?? 0)}
        </p>
      ))}
    </div>
  );
}

export interface RealtimeEventsChartProps {
  /** Serie horaria REAL de CONSULTAS (`{ ts: "HH:00", value }`), si no hay `flujo`. */
  series?: Array<{ ts: string; value: number }>;
  /** Flujo real actual vs anterior por granularidad (`derivarEstadisticas`). */
  flujo?: Partial<Record<FlujoGranularidad, FlujoPunto[]>>;
  loading?: boolean;
  error?: string | null;
}

export function RealtimeEventsChart({
  series,
  flujo,
  loading = false,
  error = null,
}: RealtimeEventsChartProps): JSX.Element {
  const [granularidad, setGranularidad] = useState<FlujoGranularidad>("hora");

  const datosDe = (id: FlujoGranularidad): FlujoPunto[] =>
    flujo?.[id] ?? (id === "hora" ? desdeSerie(series) : []);

  const hayDatos = GRANULARIDADES.some(({ id }) =>
    datosDe(id).some((punto) => punto.actual > 0 || punto.anterior > 0),
  );
  const data = datosDe(granularidad);
  const info = GRANULARIDADES.find(({ id }) => id === granularidad);
  const totalActual = sumar(data, "actual");
  const totalAnterior = sumar(data, "anterior");
  const hayAnterior = totalAnterior > 0;
  const variacion = hayAnterior ? ((totalActual - totalAnterior) / totalAnterior) * 100 : null;

  return (
    <section className="panel flex h-full min-h-0 flex-col overflow-hidden">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <div>
          <h2 className="panel-title panel-title--cap">Flujo de Consultas</h2>
          <p className="mt-1 text-xs text-muted">{info?.descripcion}</p>
        </div>
      </div>

      {loading && !hayDatos ? (
        <div
          className="flex min-h-0 flex-1 flex-col gap-3"
          role="status"
          aria-label="Cargando flujo de consultas…"
        >
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="h-3/4 w-full" />
        </div>
      ) : error && !hayDatos ? (
        <p role="alert" className="flex flex-1 items-center justify-center text-sm text-neg">
          No se pudo cargar el flujo de consultas. {error}
        </p>
      ) : !hayDatos ? (
        <p role="status" className="flex flex-1 items-center justify-center text-sm text-muted">
          SIN DATOS
        </p>
      ) : (
        <>
          <div className="mb-2 flex flex-wrap items-center justify-between gap-x-6 gap-y-2">
            <div role="group" aria-label="Granularidad" className="flex flex-wrap gap-1">
              {GRANULARIDADES.map(({ id, etiqueta }) => (
                <button
                  key={id}
                  type="button"
                  aria-pressed={granularidad === id}
                  onClick={() => setGranularidad(id)}
                  className={`rounded-[8px] border px-3 py-1 text-xs font-semibold transition-colors ${
                    granularidad === id
                      ? "border-accent bg-accent text-[#04070F]"
                      : "border-border bg-surface2 text-ink2 hover:border-accent"
                  }`}
                >
                  {etiqueta}
                </button>
              ))}
            </div>
            <p className="flex flex-wrap gap-x-4 text-xs text-ink2">
              <span>
                Actual: <span className="num font-semibold text-ink">{formatInteger(totalActual)}</span>
              </span>
              <span>
                Anterior:{" "}
                <span className="num font-semibold text-ink">{formatInteger(totalAnterior)}</span>
              </span>
              {variacion !== null ? (
                <span
                  className="num font-semibold"
                  style={{ color: variacion >= 0 ? "var(--pos)" : "var(--neg)" }}
                >
                  {variacion >= 0 ? "▲" : "▼"} {Math.abs(variacion).toFixed(1)}%
                </span>
              ) : null}
            </p>
          </div>

          <div
            className="relative min-h-0 min-w-0 flex-1 overflow-hidden"
            style={{ minHeight: 200 }}
            data-testid="chart-realtime"
          >
            <ResponsiveContainer width="100%" height="100%">
              {/* `key` re-dibuja (y re-anima) las líneas al cambiar de granularidad. */}
              <LineChart
                key={granularidad}
                data={data}
                margin={{ top: 8, right: 16, bottom: 8, left: 8 }}
              >
                <CartesianGrid stroke="var(--border)" strokeDasharray="2 6" vertical={false} />
                <XAxis
                  dataKey="label"
                  interval="preserveStartEnd"
                  minTickGap={16}
                  stroke="var(--border-strong)"
                  tick={{ fill: "var(--text-muted)", fontSize: 12 }}
                  tickLine={false}
                />
                <YAxis
                  stroke="var(--border-strong)"
                  tick={{ fill: "var(--text-muted)", fontSize: 12 }}
                  tickLine={false}
                  width={48}
                  allowDecimals={false}
                />
                <Tooltip content={<DarkTooltip />} cursor={{ stroke: "var(--accent-soft)" }} />
                <Legend verticalAlign="top" height={32} />
                <Line
                  type="monotone"
                  dataKey="actual"
                  name="Período actual"
                  stroke={COLOR_ACTUAL}
                  strokeWidth={3}
                  dot={data.length <= 12}
                  activeDot={{ r: 6 }}
                  isAnimationActive={true}
                  animationBegin={0}
                  animationDuration={1400}
                  animationEasing="ease-out"
                />
                {hayAnterior ? (
                  <Line
                    type="monotone"
                    dataKey="anterior"
                    name="Período anterior"
                    stroke={COLOR_ANTERIOR}
                    strokeDasharray="5 5"
                    strokeWidth={2}
                    dot={false}
                    isAnimationActive={true}
                    animationBegin={200}
                    animationDuration={1400}
                    animationEasing="ease-out"
                  />
                ) : null}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </>
      )}
    </section>
  );
}
