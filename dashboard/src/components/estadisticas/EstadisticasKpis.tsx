/**
 * Tarjetas KPI de la hoja `DASHBOARD_WEB` / `CONSULTAS`.
 *
 * Conecta las tarjetas SUPERIORES a los totales REALES del backend
 * (`data.totales` con fallback a `data.kpis`):
 * - Total Consultas        → `totales.total_consultas` ?? `kpis.total_consultas`.
 * - Aprehendidos           → `totales.aprehendidos` ?? `kpis.aprehendidos`.
 * - Vehículos Secuestrados → `totales.vehiculos_secuestrados` ?? `kpis.vehiculos`.
 * - Armas Secuestradas     → `totales.armas_secuestradas` ?? `kpis.armas`.
 *
 * Lenguaje visual táctico (oscuro): superficie `kpi-card`, borde tenue, número
 * blanco/cyan y un indicador lateral delgado. SIN rellenos planos rojo/verde.
 * Sin datos ⇒ 0, nunca valores inventados (tampoco `Math.random`).
 */

import type { EstadisticasKpis as EstadisticasKpisData, EstadisticasTotales } from "../../types";
import { formatInteger } from "../../lib/format";

export interface EstadisticasKpisProps {
  /** Totales reales exactos del workbook (`CONSULTAS`). */
  totales?: EstadisticasTotales;
  /** KPIs agregados; respaldo cuando `totales` no trae una clave. */
  kpis?: EstadisticasKpisData;
}

interface KpiCardProps {
  label: string;
  value: number;
  testKey: string;
}

function KpiCard({ label, value, testKey }: KpiCardProps): JSX.Element {
  return (
    <article
      className="kpi-card relative flex min-h-[128px] flex-col justify-between gap-3 overflow-hidden p-4"
      role="group"
      aria-label={`${label}: ${formatInteger(value)}`}
      data-kpi={testKey}
    >
      {/* Indicador lateral tenue: acento cyan, nunca relleno. */}
      <span
        aria-hidden="true"
        className="absolute inset-y-0 left-0 w-[3px]"
        style={{ backgroundColor: "var(--accent)" }}
      />
      <span className="label-eyebrow text-muted">{label}</span>
      <span className="kpi-value num text-[36px] font-semibold leading-[1.02] text-ink">
        {formatInteger(value)}
      </span>
    </article>
  );
}

export function EstadisticasKpis({ totales, kpis }: EstadisticasKpisProps): JSX.Element {
  const totalConsultas = totales?.total_consultas ?? kpis?.total_consultas ?? 0;
  const aprehendidos = totales?.aprehendidos ?? kpis?.aprehendidos ?? 0;
  const vehiculos = totales?.vehiculos_secuestrados ?? kpis?.vehiculos ?? 0;
  const armas = totales?.armas_secuestradas ?? kpis?.armas ?? 0;

  return (
    <div className="grid grid-cols-1 gap-[var(--grid-gutter)] sm:grid-cols-2 xl:grid-cols-4">
      <KpiCard label="TOTAL CONSULTAS" value={totalConsultas} testKey="total-consultas" />
      <KpiCard label="APREHENDIDOS" value={aprehendidos} testKey="aprehendidos" />
      <KpiCard label="VEHÍCULOS SECUESTRADOS" value={vehiculos} testKey="vehiculos-secuestrados" />
      <KpiCard label="ARMAS SECUESTRADAS" value={armas} testKey="armas-secuestradas" />
    </div>
  );
}
