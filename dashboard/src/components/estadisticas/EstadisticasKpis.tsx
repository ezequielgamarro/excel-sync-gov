/**
 * Tarjetas KPI derivadas de las intervenciones (Supabase `intervenciones_diarias`).
 *
 * Conecta las tarjetas a los totales REALES derivados (`data.totales` con
 * respaldo a `data.kpis`):
 * - Total Intervenciones   → `totales.total_intervenciones` ?? `kpis.total_intervenciones`.
 * - Total Positivos        → `totales.total_positivos` ?? `kpis.total_positivos`.
 * - Consultas de Personas  → `totales.consultas_personas` ?? `kpis.consultas_personas`.
 * - Consultas de Vehículos → `totales.consultas_vehiculos` ?? `kpis.consultas_vehiculos`.
 *
 * Lenguaje visual táctico (oscuro): superficie `kpi-card`, borde tenue, número
 * blanco/cyan y un indicador lateral delgado. SIN rellenos planos rojo/verde.
 * Sin datos ⇒ 0, nunca valores inventados (tampoco `Math.random`).
 */

import type { EstadisticasKpis as EstadisticasKpisData, EstadisticasTotales } from "../../types";
import { formatInteger } from "../../lib/format";

export interface EstadisticasKpisProps {
  /** Totales reales exactos de las intervenciones. */
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
  const totalIntervenciones = totales?.total_intervenciones ?? kpis?.total_intervenciones ?? 0;
  const totalPositivos = totales?.total_positivos ?? kpis?.total_positivos ?? 0;
  const consultasPersonas = totales?.consultas_personas ?? kpis?.consultas_personas ?? 0;
  const consultasVehiculos = totales?.consultas_vehiculos ?? kpis?.consultas_vehiculos ?? 0;

  return (
    <div className="grid grid-cols-1 gap-[var(--grid-gutter)] sm:grid-cols-2 xl:grid-cols-4">
      <KpiCard
        label="TOTAL INTERVENCIONES"
        value={totalIntervenciones}
        testKey="total-intervenciones"
      />
      <KpiCard label="TOTAL POSITIVOS" value={totalPositivos} testKey="total-positivos" />
      <KpiCard
        label="CONSULTAS DE PERSONAS"
        value={consultasPersonas}
        testKey="consultas-personas"
      />
      <KpiCard
        label="CONSULTAS DE VEHÍCULOS"
        value={consultasVehiculos}
        testKey="consultas-vehiculos"
      />
    </div>
  );
}
