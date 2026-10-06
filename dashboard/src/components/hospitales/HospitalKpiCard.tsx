/**
 * Tarjeta KPI del módulo de hospitales.
 *
 * Reutiliza el lenguaje visual de `KpiCard` (superficie oscura, borde tenue,
 * valor monoespaciado) pero sin variaciones: los totales son acumulados
 * globales de la planilla. Tolera columnas ausentes (el valor llega en 0).
 */

import type { CSSProperties } from "react";
import type { HospitalKpi } from "../../types";
import { formatInteger } from "../../lib/format";

const NEON_STYLE: CSSProperties = {
  color: "var(--accent)",
  filter: "drop-shadow(0 0 8px rgba(76, 194, 255, 0.8))",
};

const ICON_PATHS: Record<string, JSX.Element> = {
  // Cruz médica (ingresos hospitalarios).
  lesiones_culposas: (
    <>
      <path d="M10 3h4v7h7v4h-7v7h-4v-7H3v-4h7z" />
    </>
  ),
  // Pulso / actividad.
  heridos_arma_fuego: (
    <>
      <path d="M3 12h4l2-6 4 12 2-6h6" />
    </>
  ),
  // Corazón con cruz (violencia familiar / asistencia).
  violencia_familiar: (
    <>
      <path d="M12 20s-7-4.3-9.2-9A5 5 0 0 1 12 6a5 5 0 0 1 9.2 5C19 15.7 12 20 12 20z" />
      <path d="M12 10v4M10 12h4" />
    </>
  ),
  // Escudo / homicidios.
  homicidios: (
    <>
      <path d="M12 3l7 3v6c0 4.2-2.9 7.4-7 9-4.1-1.6-7-4.8-7-9V6z" />
      <path d="M12 8v4" />
      <path d="M12 15h.01" />
    </>
  ),
  // Silueta femenina (femicidio).
  femicidio: (
    <>
      <circle cx="12" cy="8" r="3.2" />
      <path d="M6 21a6 6 0 0 1 12 0" />
    </>
  ),
};

function HospitalKpiIcon({ kpiKey }: { kpiKey: string }): JSX.Element {
  return (
    <svg
      viewBox="0 0 24 24"
      width={22}
      height={22}
      aria-hidden="true"
      focusable="false"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.8}
      strokeLinecap="round"
      strokeLinejoin="round"
      className="shrink-0"
      style={NEON_STYLE}
    >
      {ICON_PATHS[kpiKey] ?? ICON_PATHS.heridos_arma_fuego}
    </svg>
  );
}

export interface HospitalKpiCardProps {
  kpi: HospitalKpi;
}

export function HospitalKpiCard({ kpi }: HospitalKpiCardProps): JSX.Element {
  return (
    <article
      className="kpi-card flex min-h-[128px] flex-col justify-between gap-3"
      role="group"
      aria-label={`${kpi.label}: ${formatInteger(kpi.value)}`}
      data-kpi={kpi.key}
    >
      <header className="flex items-start gap-2">
        <HospitalKpiIcon kpiKey={kpi.key} />
        <span
          className="label-eyebrow min-w-0 break-words text-xs leading-tight"
          title={kpi.label}
        >
          {kpi.label}
        </span>
      </header>
      <span className="kpi-value text-[36px] font-semibold leading-[1.02] text-ink" aria-hidden="true">
        {formatInteger(kpi.value)}
      </span>
      <span className="text-[11px] uppercase tracking-wide text-muted">
        {kpi.column ? "Suma global" : "Sin columna en origen"}
      </span>
    </article>
  );
}
