/**
 * Sección «Comparativas»: barras agrupadas por Jefatura Regional (mes actual vs
 * mes anterior) y área comparativa de la evolución diaria alineada.
 *
 * Es PRESENTACIONAL: recibe por props los datos derivados
 * (`IntervencionesDerivadas`), la fase, el error y el `refetch` de
 * `useIntervenciones`. Maneja `cargando`/`error`/`SIN DATOS` con los mismos
 * tokens y estados que el resto de las secciones.
 */

import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { IntervencionesDerivadas } from "../../lib/intervenciones";
import { Skeleton } from "../Skeletons";
import { TickInclinado } from "../../lib/rechartsLabels";
import { COMPARISON_LABEL, CURRENT_LABEL } from "../../lib/comparison";
import type { ComparisonPeriod } from "../../lib/comparison";

export interface ComparativasProps {
  datos: IntervencionesDerivadas | null;
  fase: "cargando" | "listo" | "error";
  error: string | null;
  refetch: () => void;
  /** Período de comparación elegido; define los rótulos de la leyenda. */
  period?: ComparisonPeriod;
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
          {entry.name}: {new Intl.NumberFormat("es-CL").format(entry.value ?? 0)}
        </p>
      ))}
    </div>
  );
}

function LoadingState(): JSX.Element {
  return (
    <div className="grid grid-cols-1 gap-[var(--grid-gutter)] xl:grid-cols-2">
      {Array.from({ length: 2 }).map((_, index) => (
        <div key={index} className="panel flex h-[320px] flex-col" aria-hidden="true">
          <Skeleton className="mb-6 h-4 w-1/2" />
          <Skeleton className="h-4/5 w-full" />
        </div>
      ))}
    </div>
  );
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }): JSX.Element {
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center gap-3 rounded-[12px] border border-neg/50 bg-surface px-4 py-3 text-sm font-semibold text-neg"
    >
      <span aria-hidden="true">⛔</span>
      <span className="flex-1">No se pudieron cargar las comparativas. {message}</span>
      <button
        type="button"
        onClick={onRetry}
        className="touch-target rounded-[10px] border border-neg/60 bg-surface px-4 py-2 text-xs font-semibold uppercase tracking-wide text-ink transition-colors hover:border-accent hover:text-accent"
      >
        Reintentar
      </button>
    </div>
  );
}

export function Comparativas({
  datos,
  fase,
  error,
  refetch,
  period = "mes",
}: ComparativasProps): JSX.Element {
  if (fase === "cargando") {
    return <LoadingState />;
  }

  if (fase === "error" || !datos) {
    return <ErrorState message={error ?? "Error desconocido."} onRetry={refetch} />;
  }

  const regional = datos.comparativa_regional ?? [];
  const diaria = datos.comparativa_diaria ?? [];

  if (regional.length === 0 && diaria.length === 0) {
    return (
      <div className="panel flex min-h-[320px] items-center justify-center">
        <p role="status" className="text-sm text-muted">
          SIN DATOS
        </p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-[var(--grid-gutter)] xl:grid-cols-2">
      <section className="panel flex h-[380px] min-h-0 flex-col overflow-hidden">
        <h2 className="panel-title panel-title--cap mb-3">Comparativa por Unidad Regional</h2>
        <div
          className="relative min-h-0 min-w-0 flex-1 overflow-hidden"
          style={{ minHeight: 220 }}
          data-testid="chart-comparativas-regional"
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={regional} margin={{ top: 16, right: 16, bottom: 8, left: 0 }}>
              <CartesianGrid stroke="var(--border)" strokeDasharray="2 6" vertical={false} />
              <XAxis
                dataKey="name"
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
                width={56}
                allowDecimals={false}
              />
              <Tooltip content={<DarkTooltip />} cursor={{ fill: "var(--accent-soft)" }} />
              <Legend verticalAlign="top" height={36} />
              <Bar
                dataKey="mesActual"
                name={CURRENT_LABEL[period]}
                fill="#22c55e"
                isAnimationActive={true}
                animationBegin={0}
                animationDuration={1200}
                animationEasing="ease-out"
              />
              <Bar
                dataKey="mesAnterior"
                name={COMPARISON_LABEL[period]}
                fill="#64748b"
                isAnimationActive={true}
                animationBegin={0}
                animationDuration={1200}
                animationEasing="ease-out"
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>

      <section className="panel flex h-[380px] min-h-0 flex-col overflow-hidden">
        <h2 className="panel-title panel-title--cap mb-3">Evolución Diaria Comparada</h2>
        <div
          className="relative min-h-0 min-w-0 flex-1 overflow-hidden"
          style={{ minHeight: 220 }}
          data-testid="chart-comparativas-diaria"
        >
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={diaria} margin={{ top: 16, right: 16, bottom: 8, left: 0 }}>
              <CartesianGrid stroke="var(--border)" strokeDasharray="2 6" vertical={false} />
              <XAxis
                dataKey="fecha"
                stroke="var(--border-strong)"
                tick={{ fill: "var(--text-secondary)", fontSize: 12 }}
                tickLine={false}
              />
              <YAxis
                stroke="var(--border-strong)"
                tick={{ fill: "var(--text-muted)", fontSize: 12 }}
                tickLine={false}
                width={56}
                allowDecimals={false}
              />
              <Tooltip content={<DarkTooltip />} cursor={{ stroke: "var(--accent-soft)" }} />
              <Legend verticalAlign="top" height={36} />
              <Area
                dataKey="actual"
                name="Actual"
                stroke="#3b82f6"
                fill="#3b82f6"
                fillOpacity={0.25}
                isAnimationActive={true}
                animationBegin={0}
                animationDuration={1200}
                animationEasing="ease-out"
              />
              <Area
                dataKey="anterior"
                name="Anterior"
                stroke="#64748b"
                fill="#64748b"
                fillOpacity={0.15}
                isAnimationActive={true}
                animationBegin={0}
                animationDuration={1200}
                animationEasing="ease-out"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </section>
    </div>
  );
}
