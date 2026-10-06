/**
 * Módulo «Ingresos Hospitalarios»: KPIs y distribución de causas delictivas a
 * partir de `GET /api/hospitales/estadisticas`.
 *
 * - Panel superior de tarjetas KPI (suma global por causa clave).
 * - Barras con la distribución de las causas delictivas (ancho completo).
 * - Estados de carga (skeleton), error (banner con reintento) y vacío.
 * - Diseño táctico oscuro con los tokens institucionales.
 */

import { Skeleton } from "../components/Skeletons";
import { HospitalKpiCard } from "../components/hospitales/HospitalKpiCard";
import { HospitalBarsChart } from "../components/hospitales/HospitalBarsChart";
import { useHospitales } from "../hooks/useHospitales";
import { computeHospitalKpis } from "../lib/hospitales";
import { formatInteger } from "../lib/format";

const CHART_HEIGHT = 360;

function KpiGridSkeleton(): JSX.Element {
  return (
    <div className="grid grid-cols-1 gap-[var(--grid-gutter)] sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
      {Array.from({ length: 5 }).map((_, index) => (
        <div
          key={index}
          className="kpi-card flex min-h-[128px] flex-col justify-between gap-3"
          aria-hidden="true"
        >
          <Skeleton className="h-3 w-3/4" />
          <Skeleton className="h-9 w-1/2" />
          <Skeleton className="h-3 w-1/3" />
        </div>
      ))}
    </div>
  );
}

function ErrorBanner({ message, onRetry }: { message: string; onRetry: () => void }): JSX.Element {
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center gap-3 rounded-[12px] border border-neg/50 bg-neg/10 px-4 py-3 text-sm font-semibold text-neg"
    >
      <span aria-hidden="true">⛔</span>
      <span className="flex-1">
        No se pudieron cargar las estadísticas de hospitales. {message}
      </span>
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

export function HospitalDashboard(): JSX.Element {
  const { data, loading, error, reload } = useHospitales();

  const header = (
    <div>
      <h2 className="font-display text-xl font-semibold uppercase tracking-wide text-ink">
        Ingresos Hospitalarios
      </h2>
      <p className="text-sm text-muted">
        Estadísticas agregadas de la planilla de hospitales
        {data ? ` · ${data.sheet} · ${formatInteger(data.total_rows)} registros` : ""}
      </p>
    </div>
  );

  if (loading) {
    return (
      <div className="flex flex-col gap-6">
        {header}
        <KpiGridSkeleton />
        <div
          className="panel w-full"
          style={{ height: CHART_HEIGHT }}
          role="status"
          aria-label="Cargando distribución de causas…"
        >
          <Skeleton className="mb-6 h-4 w-1/2" />
          <Skeleton className="h-full w-full" />
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col gap-6">
        {header}
        <ErrorBanner message={error} onRetry={reload} />
      </div>
    );
  }

  if (!data || data.rows.length === 0) {
    return (
      <div className="flex flex-col gap-6">
        {header}
        <section className="panel" role="status">
          <h3 className="panel-title panel-title--cap mb-2">Sin datos</h3>
          <p className="text-sm text-muted">
            La planilla de hospitales no contiene filas para mostrar.
          </p>
        </section>
      </div>
    );
  }

  const kpis = computeHospitalKpis(data);
  const chartData = data.chartData ?? [];

  return (
    <div className="flex flex-col gap-6">
      {header}

      <div className="grid grid-cols-1 gap-[var(--grid-gutter)] sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-5">
        {kpis.map((kpi) => (
          <div key={kpi.key} className="min-w-0">
            <HospitalKpiCard kpi={kpi} />
          </div>
        ))}
      </div>

      <div className="col-span-full w-full min-w-0" style={{ height: CHART_HEIGHT }}>
        <HospitalBarsChart
          title="Distribución de Causas Delictivas"
          subtitle="Suma global por columna"
          data={chartData}
          gradientId="hospitalCausesGradient"
          testId="chart-hospital-causas"
        />
      </div>
    </div>
  );
}
