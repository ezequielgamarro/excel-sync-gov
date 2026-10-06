/**
 * Cabecera superior del panel: título, estado de conexión/reloj, buscador global,
 * selector de comparación y perfil del oficial.
 */

import { ConnectionStatus } from "./ConnectionStatus";
import { ComparisonBar } from "./ComparisonBar";
import type { ConnectionPhase } from "../state/dashboardReducer";
import type { AuthSession } from "../auth/session";
import { formatClock } from "../lib/format";

export interface HeaderProps {
  now: number;
  tz: string;
  phase: ConnectionPhase;
  attempt: number;
  degraded: boolean;
  lastUpdatedAt: number | null;
  session: AuthSession | null;
  onLogout: () => void;
  /** Abre el drawer del sidebar en pantallas pequeñas. */
  onOpenSidebar?: () => void;
  /** Estado del drawer (para `aria-expanded`). */
  sidebarOpen?: boolean;
}

/** Recorta identificadores largos (p. ej. UUID) para no ensanchar la cabecera. */
function shortId(value?: string): string {
  if (!value) return "—";
  return value.length > 8 ? `${value.slice(0, 8)}…` : value;
}

export function Header({
  now,
  tz,
  phase,
  attempt,
  degraded,
  lastUpdatedAt,
  session,
  onLogout,
  onOpenSidebar,
  sidebarOpen = false,
}: HeaderProps): JSX.Element {
  const role = session?.roles[0] ?? session?.capabilities[0] ?? "—";
  return (
    <header className="flex flex-col gap-3 border-b border-border bg-surface/70 px-4 py-3 backdrop-blur sm:px-6">
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2">
        <div className="flex min-w-0 items-center gap-3">
          {onOpenSidebar ? (
            <button
              type="button"
              onClick={onOpenSidebar}
              aria-label="Abrir menú de navegación"
              aria-controls="admin-sidebar"
              aria-expanded={sidebarOpen}
              className="touch-target -ml-2 flex shrink-0 items-center justify-center rounded-[10px] border border-border text-ink2 transition-colors hover:border-accent hover:text-accent lg:hidden"
            >
              <svg
                viewBox="0 0 24 24"
                width={20}
                height={20}
                fill="none"
                stroke="currentColor"
                strokeWidth={1.8}
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M4 6h16" />
                <path d="M4 12h16" />
                <path d="M4 18h16" />
              </svg>
            </button>
          ) : null}

          <div className="min-w-0">
            <h1
              className="truncate font-display text-[clamp(16px,1.1vw,21px)] font-semibold uppercase leading-tight tracking-[0.02em] text-ink"
              translate="no"
            >
              Informe Operativo Comparativo
            </h1>
            <p
              className="truncate text-[11px] font-medium uppercase tracking-[0.08em] text-muted"
              translate="no"
            >
              Centro Integrador de Sistemas y Operaciones
            </p>
          </div>
        </div>

        <div className="flex w-full min-w-0 flex-wrap items-center gap-x-5 gap-y-1 sm:w-auto sm:shrink-0">
          <ConnectionStatus
            phase={phase}
            attempt={attempt}
            degraded={degraded}
            lastUpdatedAt={lastUpdatedAt}
          />
          <div
            className="flex min-w-0 flex-col items-end leading-tight"
            title={`Zona horaria canónica: ${tz}`}
          >
            <span className="num text-sm text-ink2">{formatClock(new Date(now))}</span>
            <span className="max-w-full truncate text-[11px] text-muted">{tz}</span>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
        <ComparisonBar />

        <div className="ml-auto flex items-center gap-3 border-l border-border pl-4">
          <div className="flex flex-col items-end leading-tight">
            <span className="text-[11px] uppercase tracking-wide text-muted">Oficial</span>
            <span className="text-xs text-ink2" title={session?.sub || "—"}>
              {shortId(session?.sub)} <span className="text-muted">{role}</span>
            </span>
          </div>
          <button
            type="button"
            onClick={onLogout}
            className="touch-target shrink-0 rounded-full border border-border px-4 text-xs font-semibold text-ink2 transition-colors hover:border-accent hover:text-accent"
          >
            Salir
          </button>
        </div>
      </div>
    </header>
  );
}
