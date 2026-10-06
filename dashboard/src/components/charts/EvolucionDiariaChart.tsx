/**
 * «Evolución Diaria de Incidentes».
 *
 * Grafica la serie REAL de incidentes por día (`{ fecha, total }`):
 * `<XAxis dataKey="fecha" />` (días `DD/MM`) y una única serie
 * `<Bar dataKey="total" />` en azul/cyan, con tooltip oscuro y estados
 * `loading`/`error`/`SIN DATOS`. No hay generadores de datos: sin serie, la UI
 * muestra «SIN DATOS».
 */

import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { IncidenteFecha } from "../../types";
import { formatInteger } from "../../lib/format";
import { usePrefersReducedMotion } from "../../hooks/useAnimatedNumber";
import { Skeleton } from "../Skeletons";

export const EVOLUCION_DIARIA_COLOR = "#4cc2ff";

export interface EvolucionDiariaChartProps {
  /** Incidentes por día (`{ fecha: "DD/MM", total }`), orden cronológico. */
  data?: IncidenteFecha[];
  loading?: boolean;
  error?: string | null;
  title?: string;
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
          {entry.name}: {formatInteger(entry.value ?? 0)}
        </p>
      ))}
    </div>
  );
}

export function EvolucionDiariaChart({
  data,
  loading = false,
  error = null,
  title = "Evolución Diaria de Incidentes",
}: EvolucionDiariaChartProps): JSX.Element {
  const reducedMotion = usePrefersReducedMotion();
  const rows = (data ?? []).filter((item) => item && String(item.fecha).trim() !== "");

  return (
    <section className="panel flex h-full min-h-0 flex-col overflow-hidden">
      <h2 className="panel-title panel-title--cap mb-3">{title}</h2>

      {loading && rows.length === 0 ? (
        <div
          className="flex min-h-0 flex-1 flex-col gap-3"
          role="status"
          aria-label={`Cargando ${title}…`}
        >
          <Skeleton className="h-4 w-1/2" />
          <Skeleton className="h-3/4 w-full" />
        </div>
      ) : error && rows.length === 0 ? (
        <p role="alert" className="flex flex-1 items-center justify-center text-sm text-neg">
          No se pudieron cargar los datos. {error}
        </p>
      ) : rows.length === 0 ? (
        <p role="status" className="flex flex-1 items-center justify-center text-sm text-muted">
          SIN DATOS
        </p>
      ) : (
        <div
          className="relative min-h-0 min-w-0 flex-1 overflow-hidden"
          style={{ minHeight: 180 }}
          data-testid="chart-evolucion-diaria"
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={rows} margin={{ top: 16, right: 16, bottom: 8, left: 0 }}>
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
              <Tooltip content={<DarkTooltip />} cursor={{ fill: "var(--accent-soft)" }} />
              <Bar
                dataKey="total"
                name="INCIDENTES"
                fill={EVOLUCION_DIARIA_COLOR}
                radius={[4, 4, 0, 0]}
                isAnimationActive={!reducedMotion}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}
