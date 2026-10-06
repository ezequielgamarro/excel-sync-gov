/**
 * Estado de conexión textual y con color:
 * EN VIVO / RECONECTANDO / DEGRADADO · POLLING / SIN CONEXIÓN.
 * Incluye la hora de la última actualización de datos.
 */

import type { ConnectionPhase } from "../state/dashboardReducer";

export interface ConnectionStatusProps {
  phase: ConnectionPhase;
  attempt: number;
  degraded: boolean;
  lastUpdatedAt: number | null;
}

interface Descriptor {
  label: string;
  dot: string;
  text: string;
  glyph: string;
}

function describe(phase: ConnectionPhase, attempt: number, degraded: boolean): Descriptor {
  if (degraded || phase === "degraded") {
    return {
      label: "DEGRADADO · POLLING (10 s)",
      dot: "var(--warn)",
      text: "var(--warn)",
      glyph: "◐",
    };
  }
  switch (phase) {
    case "live":
      return { label: "EN VIVO", dot: "var(--pos)", text: "var(--pos)", glyph: "●" };
    case "reconnecting":
      return {
        label: `RECONECTANDO (intento ${attempt})`,
        dot: "var(--warn)",
        text: "var(--warn)",
        glyph: "↻",
      };
    case "offline":
      return { label: "SIN CONEXIÓN", dot: "var(--neg)", text: "var(--neg)", glyph: "✕" };
    default:
      return {
        label: "CONECTANDO…",
        dot: "var(--muted)",
        text: "var(--muted)",
        glyph: "…",
      };
  }
}

function formatLastUpdate(ts: number | null): string {
  if (!ts) return "—";
  try {
    return new Intl.DateTimeFormat("es-CL", {
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }).format(new Date(ts));
  } catch {
    return new Date(ts).toISOString().slice(11, 19);
  }
}

export function ConnectionStatus({
  phase,
  attempt,
  degraded,
  lastUpdatedAt,
}: ConnectionStatusProps): JSX.Element {
  const descriptor = describe(phase, attempt, degraded);
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
      <span
        className="flex items-center gap-2 text-sm font-semibold"
        style={{ color: descriptor.text }}
        role="status"
        aria-live="polite"
      >
        <span aria-hidden="true">{descriptor.glyph}</span>
        {descriptor.label}
      </span>
      <span className="flex flex-col items-end leading-tight">
        <span className="text-[11px] uppercase tracking-wide text-muted">Última actualización</span>
        <span className="num text-xs text-ink2">{formatLastUpdate(lastUpdatedAt)}</span>
      </span>
    </div>
  );
}
