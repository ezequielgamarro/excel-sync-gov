import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { usePrefersReducedMotion } from "../../hooks/useAnimatedNumber";
import { FilterBar } from "../tabs/FilterBar";
import { Skeleton } from "../Skeletons";

interface Point {
  t: number;
  eventos: number;
}

function formatClock(t: number): string {
  return new Intl.DateTimeFormat("es-AR", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  }).format(new Date(t));
}

interface TooltipEntry {
  name?: string;
  value?: number;
  color?: string;
}

interface TooltipProps {
  active?: boolean;
  label?: number;
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
      <p className="num text-xs text-muted">
        {typeof label === "number" ? formatClock(label) : ""}
      </p>
      {payload.map((entry) => (
        <p key={entry.name} className="num mt-1" style={{ color: entry.color }}>
          {entry.name}: {new Intl.NumberFormat("es-CL").format(entry.value ?? 0)}
        </p>
      ))}
    </div>
  );
}

export interface RealtimeEventsChartProps {
  /** Serie temporal REAL de CONSULTAS (`{ ts, value }`). */
  series?: Array<{ ts: string; value: number }>;
  loading?: boolean;
  error?: string | null;
}

/** Flujo de eventos en el tiempo a partir de la serie real de CONSULTAS. */
export function RealtimeEventsChart({
  series,
  loading = false,
  error = null,
}: RealtimeEventsChartProps): JSX.Element {
  const reducedMotion = usePrefersReducedMotion();
  const data: Point[] = (series ?? [])
    .map((point) => ({ t: Date.parse(point.ts), eventos: point.value }))
    .filter((point) => Number.isFinite(point.t))
    .sort((a, b) => a.t - b.t);

  return (
    <section className="panel flex h-full min-h-0 flex-col overflow-hidden">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="panel-title panel-title--cap">Flujo de Eventos en Tiempo Real</h2>
        <FilterBar />
      </div>

      {loading && data.length === 0 ? (
        <div
          className="flex min-h-0 flex-1 flex-col gap-3"
          role="status"
          aria-label="Cargando flujo de eventos…"
        >
          <Skeleton className="h-4 w-1/3" />
          <Skeleton className="h-3/4 w-full" />
        </div>
      ) : error && data.length === 0 ? (
        <p role="alert" className="flex flex-1 items-center justify-center text-sm text-neg">
          No se pudo cargar el flujo de eventos. {error}
        </p>
      ) : data.length === 0 ? (
        <p role="status" className="flex flex-1 items-center justify-center text-sm text-muted">
          SIN DATOS
        </p>
      ) : (
        <div
          className="relative min-h-0 min-w-0 flex-1 overflow-hidden"
          data-testid="chart-realtime"
        >
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
              <CartesianGrid stroke="var(--border)" strokeDasharray="2 6" vertical={false} />
              <XAxis
                dataKey="t"
                type="number"
                scale="time"
                domain={["dataMin", "dataMax"]}
                tickFormatter={formatClock}
                stroke="var(--border-strong)"
                tick={{ fill: "var(--text-muted)", fontSize: 12 }}
                tickLine={false}
              />
              <YAxis
                stroke="var(--border-strong)"
                tick={{ fill: "var(--text-muted)", fontSize: 12 }}
                tickLine={false}
                width={56}
              />
              <Tooltip content={<DarkTooltip />} cursor={{ stroke: "var(--accent-soft)" }} />
              <Line
                type="monotone"
                dataKey="eventos"
                name="Eventos"
                stroke="#4cc2ff"
                strokeWidth={2}
                dot={false}
                isAnimationActive={!reducedMotion}
              />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </section>
  );
}
