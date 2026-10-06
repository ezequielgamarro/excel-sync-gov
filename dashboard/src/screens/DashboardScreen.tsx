/**
 * Pantalla principal (panel de administración táctico): sidebar fijo + cabecera
 * + contenido scrolleable. El documento no scrollea; el scroll vive en el `main`.
 *
 * Datos:
 * - Resumen y Comparativas: snapshot (`indicators.snapshot`) + `DASHBOARD_WEB`.
 * - Incidentes/Logística/Estadísticas: fuente PRIMARIA `GET /api/estadisticas`
 *   (Excel real traducido) vía `useEstadisticas`; `useConsultas` sólo como
 *   respaldo. Sin ambos orígenes → estado vacío, nunca demo.
 */

import { useEffect, useState } from "react";
import type { AuthSession } from "../auth/session";
import { useDashboard } from "../hooks/useDashboard";
import { KPI_LABEL, KPI_ORDER } from "../types";
import type { IncidenteFecha, Kpi, KpiKey } from "../types";
import { Header } from "../components/Header";
import { KpiCard } from "../components/KpiCard";
import { KpiSkeleton, TableSkeleton } from "../components/Skeletons";
import {
  InvalidDataBanner,
  PartialDataNotice,
  SchemaErrorBanner,
  StaleBanner,
} from "../components/Banners";
import { FilterBar } from "../components/tabs/FilterBar";
import { AdminSidebar } from "../components/layout/AdminSidebar";
import { HelpScreen } from "./HelpScreen";
import { HospitalDashboard } from "./HospitalDashboard";
import { COMPARISON_LABEL } from "../lib/comparison";
import { formatInteger } from "../lib/format";
import { useComparison } from "../state/ComparisonContext";
import { useFilters } from "../state/FiltersContext";
import { RealtimeEventsChart } from "../components/charts/RealtimeEventsChart";
import { TurnosColumnsChart } from "../components/charts/TurnosColumnsChart";
import { DistributionDonutChart } from "../components/charts/DistributionDonutChart";
import { EvolucionDiariaChart } from "../components/charts/EvolucionDiariaChart";
import { BarrasHorizontalesChart } from "../components/charts/BarrasHorizontalesChart";
import { EstadisticasSection } from "../components/estadisticas/EstadisticasSection";
import { RankingTop5Table } from "../components/estadisticas/RankingTop5Table";
import { useConsultas } from "../hooks/useConsultas";
import { useEstadisticas } from "../hooks/useEstadisticas";
import { aGrupos, aSerie } from "../lib/estadisticas";

export interface DashboardScreenProps {
  session: AuthSession | null;
  onLogout: () => void;
}

const CHART_HEIGHT = 260;
const TABLE_HEIGHT = 340;

/** Mapa sección ↔ hash de URL (sin React Router). */
const HASH_BY_ID: Record<string, string> = {
  resumen: "#/resumen",
  incidentes: "#/incidentes",
  logistica: "#/logistica",
  estadisticas: "#/estadisticas",
  hospitales: "#/hospitales",
  comparativas: "#/comparativas",
  ayuda: "#/ayuda",
};

const ID_BY_HASH: Record<string, string> = Object.fromEntries(
  Object.entries(HASH_BY_ID).map(([id, hash]) => [hash, id]),
);

export function DashboardScreen({ session, onLogout }: DashboardScreenProps): JSX.Element {
  const { state, stale, now, lastSyncAt } = useDashboard(true);
  const [activeTab, setActiveTab] = useState<string>(
    () => ID_BY_HASH[window.location.hash] ?? "resumen",
  );
  const [sidebarOpen, setSidebarOpen] = useState(false);

  const selectTab = (id: string): void => {
    setActiveTab(id);
    setSidebarOpen(false);
    const hash = HASH_BY_ID[id];
    if (hash && window.location.hash !== hash) {
      window.location.hash = hash;
    }
  };

  // Sincroniza la navegación con atrás/adelante del navegador.
  useEffect(() => {
    const onHashChange = (): void => {
      const id = ID_BY_HASH[window.location.hash];
      if (id) setActiveTab(id);
    };
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);
  const { filters, setUnidadesDisponibles } = useFilters();
  const { period: comparisonPeriod } = useComparison();

  const snapshot = state.snapshot;
  const tz = snapshot?.tz ?? "America/Argentina/Buenos_Aires";
  const ageSeconds = Math.max(0, (now - lastSyncAt) / 1000);

  // Respaldo de agregación de CONSULTAS; la fuente primaria de Incidentes/
  // Logística/Estadísticas es `estadisticas` (ver más abajo).
  const { aggregation, loading: consultasLoading, error: consultasError } = useConsultas(filters);

  // Datos reales de la hoja DASHBOARD_WEB (Resumen y Comparativas).
  const {
    datos: estadisticas,
    fase: estadisticasFase,
    error: estadisticasError,
  } = useEstadisticas(comparisonPeriod);
  const gruposComparativas = aGrupos(estadisticas?.comparativas);

  // Selector de Unidad Regional DINÁMICO: catálogo real del backend para el
  // rango/período activo (no estático).
  useEffect(() => {
    setUnidadesDisponibles(estadisticas?.regionales_disponibles ?? []);
  }, [estadisticas?.regionales_disponibles, setUnidadesDisponibles]);

  // Fuente PRIMARIA de Incidentes/Logística/Estadísticas: `GET /api/estadisticas`
  // (Excel real, claves traducidas a español). `aggregation` (CONSULTAS) queda
  // como respaldo si el endpoint no trajera una serie. Sin ambos → SIN DATOS.
  const chartsLoading = estadisticasFase === "cargando" || consultasLoading;
  const chartsError = estadisticasError ?? consultasError;

  const serieIncidentes = aSerie(estadisticas?.incidentes_por_dia);
  const seriesTemporal = serieIncidentes.length > 0 ? serieIncidentes : (aggregation?.series ?? []);

  const gruposUnidad = aGrupos(
    estadisticas?.intervenciones_por_unidad ?? estadisticas?.grafico_regionales,
  );
  const gruposUnidadFinal =
    gruposUnidad.length > 0 ? gruposUnidad : (aggregation?.by_jefatura_regional ?? []);

  // Evolución DIARIA REAL: serie estricta por fecha; si falta, se deriva de
  // `incidentes_turno_por_dia` (mañana+tarde+noche) o del respaldo de CONSULTAS.
  const serieDiaria: IncidenteFecha[] =
    estadisticas?.incidentes_por_fecha && estadisticas.incidentes_por_fecha.length > 0
      ? estadisticas.incidentes_por_fecha
      : (estadisticas?.incidentes_turno_por_dia ?? []).length > 0
        ? (estadisticas?.incidentes_turno_por_dia ?? []).map((dia) => ({
            fecha: dia.fecha,
            total: dia.mañana + dia.tarde + dia.noche,
          }))
        : (aggregation?.series ?? []).map((punto) => ({
            fecha: punto.ts,
            total: punto.value,
          }));

  const gruposTipo = aGrupos(
    estadisticas?.distribucion_incidentes ?? estadisticas?.incidentes_por_tipo,
  );
  const gruposTipoFinal =
    gruposTipo.length > 0 ? gruposTipo : (aggregation?.by_causas_penales ?? []);

  const kpisLogistica = estadisticas?.kpis;
  const vehiculosLogistica =
    aggregation?.kpis.vehiculos_secuestrados ?? kpisLogistica?.vehiculos ?? null;
  const armasLogistica = aggregation?.kpis.armas_secuestradas ?? kpisLogistica?.armas ?? null;
  const hayLogistica = vehiculosLogistica !== null || armasLogistica !== null;

  // KPIs SUPERIORES conectados a los TOTALES REALES de `estadisticas` (sin
  // semillas): `totales` con respaldo `kpis`. Sin referencia histórica real, la
  // tarjeta muestra «— sin {período}» (nunca baseline inventado).
  const valoresKpi: Record<KpiKey, number> = {
    total_consultas_sifcop:
      estadisticas?.totales?.total_consultas ?? estadisticas?.kpis?.total_consultas ?? 0,
    personas_capturadas:
      estadisticas?.totales?.aprehendidos ?? estadisticas?.kpis?.aprehendidos ?? 0,
    vehiculos_secuestrados:
      estadisticas?.totales?.vehiculos_secuestrados ?? estadisticas?.kpis?.vehiculos ?? 0,
    armas_secuestradas: estadisticas?.totales?.armas_secuestradas ?? estadisticas?.kpis?.armas ?? 0,
  };

  const kpiReal = (key: KpiKey): Kpi => ({
    label: KPI_LABEL[key],
    value: valoresKpi[key],
    delta_abs: null,
    delta_pct: null,
    direction: "flat",
    comparison: "ayer_mismo_tramo",
    baseline_value: 0,
    as_of: "",
    has_reference: false,
  });

  const kpiRow = (
    <div className="grid grid-cols-1 gap-[var(--grid-gutter)] sm:grid-cols-2 xl:grid-cols-4">
      {estadisticasFase === "cargando"
        ? KPI_ORDER.map((key) => (
            <div key={key} className="min-w-0">
              <KpiSkeleton />
            </div>
          ))
        : KPI_ORDER.map((key) => (
            <div key={key} className="min-w-0">
              <KpiCard
                kpiKey={key}
                kpi={kpiReal(key)}
                periodLabel={COMPARISON_LABEL[comparisonPeriod]}
                dimmed={stale}
              />
            </div>
          ))}
    </div>
  );

  return (
    <>
      <a className="skip-link" href="#contenido">
        Saltar al contenido
      </a>
      <div className="admin-shell flex overflow-hidden">
        <AdminSidebar
          activeTab={activeTab}
          onSelect={selectTab}
          open={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
        />

        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
          <Header
            now={now}
            tz={tz}
            phase={state.phase}
            attempt={state.attempt}
            degraded={state.degraded}
            lastUpdatedAt={lastSyncAt}
            session={session}
            onLogout={onLogout}
            onOpenSidebar={() => setSidebarOpen(true)}
            sidebarOpen={sidebarOpen}
          />

          <main id="contenido" className="dash-enter min-h-0 flex-1 overflow-y-auto p-4 sm:p-6">
            {state.schemaError ? (
              <div className="mb-4">
                <SchemaErrorBanner />
              </div>
            ) : null}
            {state.invalidData ? (
              <div className="mb-4">
                <InvalidDataBanner />
              </div>
            ) : null}
            {stale ? (
              <div className="mb-4">
                <StaleBanner ageSeconds={ageSeconds} />
              </div>
            ) : null}

            {activeTab === "ayuda" ? <HelpScreen /> : null}

            {activeTab === "resumen" ? (
              <div className="flex flex-col gap-6">
                {kpiRow}

                <div className="panel flex flex-wrap items-center gap-3 py-1">
                  <FilterBar layout="inline" />
                </div>

                {/* Series reales de la hoja DASHBOARD_WEB (sin datos demo). */}
                <EstadisticasSection />

                {/* Gráficos reales de `GET /api/estadisticas` (sin semillas). */}
                <div className="grid grid-cols-1 gap-[var(--grid-gutter)] xl:grid-cols-2">
                  <div className="min-w-0" style={{ height: CHART_HEIGHT }}>
                    <EvolucionDiariaChart
                      data={serieDiaria}
                      loading={chartsLoading}
                      error={chartsError}
                    />
                  </div>
                  <div className="min-w-0" style={{ height: CHART_HEIGHT }}>
                    <TurnosColumnsChart
                      mode="unidad"
                      title="Intervenciones por Unidad Regional"
                      testId="chart-columns-unidad"
                      groups={gruposUnidadFinal}
                      loading={chartsLoading}
                      error={chartsError}
                    />
                  </div>
                </div>

                {/* Ranking Top 5 REAL (datos.rankingTop5; sin ranking semilla). */}
                <div className="flex flex-col gap-[var(--grid-gutter)]">
                  <div className="min-w-0" style={{ height: TABLE_HEIGHT }}>
                    {snapshot?.payload.quality.partial ? <PartialDataNotice /> : null}
                    <RankingTop5Table
                      data={estadisticas?.rankingTop5}
                      loading={estadisticasFase === "cargando"}
                      error={estadisticasError}
                    />
                  </div>
                </div>
              </div>
            ) : null}

            {activeTab === "incidentes" ? (
              <div className="grid grid-cols-1 gap-[var(--grid-gutter)] xl:grid-cols-2">
                <div className="min-w-0" style={{ height: CHART_HEIGHT }}>
                  <RealtimeEventsChart
                    series={seriesTemporal}
                    loading={chartsLoading}
                    error={chartsError}
                  />
                </div>
                <div className="min-w-0" style={{ height: CHART_HEIGHT }}>
                  <TurnosColumnsChart
                    mode="unidad"
                    title="Intervenciones por Unidad Regional"
                    testId="chart-columns-unidad"
                    groups={gruposUnidadFinal}
                    loading={chartsLoading}
                    error={chartsError}
                  />
                </div>
              </div>
            ) : null}

            {activeTab === "logistica" ? (
              <div className="flex flex-col gap-[var(--grid-gutter)]">
                {hayLogistica ? (
                  <div className="panel flex flex-wrap items-center gap-6 py-3">
                    <span className="flex items-baseline gap-2">
                      <span className="text-[11px] uppercase tracking-wide text-muted">
                        Vehículos secuestrados
                      </span>
                      <span className="num text-xl font-semibold text-ink">
                        {formatInteger(vehiculosLogistica ?? 0)}
                      </span>
                    </span>
                    <span className="flex items-baseline gap-2">
                      <span className="text-[11px] uppercase tracking-wide text-muted">
                        Armas secuestradas
                      </span>
                      <span className="num text-xl font-semibold text-ink">
                        {formatInteger(armasLogistica ?? 0)}
                      </span>
                    </span>
                  </div>
                ) : null}
                {/* Logística REAL: barras HORIZONTALES por Unidad Regional. */}
                <div className="min-w-0">
                  <BarrasHorizontalesChart
                    title="Vehículos Secuestrados por Regional"
                    testId="chart-logistica-vehiculos"
                    data={
                      estadisticas?.vehiculosPorRegional ??
                      estadisticas?.logistica_vehiculos_por_regional
                    }
                    loading={chartsLoading}
                    error={chartsError}
                  />
                </div>
                <div className="min-w-0">
                  <BarrasHorizontalesChart
                    title="Armas Secuestradas por Regional"
                    testId="chart-logistica-armas"
                    data={
                      estadisticas?.armasPorRegional ?? estadisticas?.logistica_armas_por_regional
                    }
                    loading={chartsLoading}
                    error={chartsError}
                  />
                </div>
              </div>
            ) : null}

            {activeTab === "estadisticas" ? (
              <div className="flex flex-col gap-[var(--grid-gutter)]">
                <div className="grid grid-cols-1 gap-[var(--grid-gutter)] xl:grid-cols-2 2xl:grid-cols-3">
                  <div className="min-w-0" style={{ height: CHART_HEIGHT }}>
                    <EvolucionDiariaChart
                      data={serieDiaria}
                      loading={chartsLoading}
                      error={chartsError}
                    />
                  </div>
                  <div className="min-w-0" style={{ height: CHART_HEIGHT }}>
                    <TurnosColumnsChart
                      mode="unidad"
                      title="Intervenciones por Unidad Regional"
                      testId="chart-columns-unidad"
                      groups={gruposUnidadFinal}
                      loading={chartsLoading}
                      error={chartsError}
                    />
                  </div>
                  <div className="min-w-0" style={{ height: CHART_HEIGHT }}>
                    <DistributionDonutChart
                      title="Distribución por Tipo"
                      groups={gruposTipoFinal}
                      loading={chartsLoading}
                      error={chartsError}
                    />
                  </div>
                  <div className="min-w-0" style={{ height: CHART_HEIGHT }}>
                    <RealtimeEventsChart
                      series={seriesTemporal}
                      loading={chartsLoading}
                      error={chartsError}
                    />
                  </div>
                  <div className="min-w-0">
                    <BarrasHorizontalesChart
                      title="Vehículos Secuestrados por Regional"
                      testId="chart-logistica-vehiculos"
                      data={
                        estadisticas?.vehiculosPorRegional ??
                        estadisticas?.logistica_vehiculos_por_regional
                      }
                      loading={chartsLoading}
                      error={chartsError}
                    />
                  </div>
                  <div className="min-w-0">
                    <BarrasHorizontalesChart
                      title="Armas Secuestradas por Regional"
                      testId="chart-logistica-armas"
                      data={
                        estadisticas?.armasPorRegional ?? estadisticas?.logistica_armas_por_regional
                      }
                      loading={chartsLoading}
                      error={chartsError}
                    />
                  </div>
                </div>

                <div className="min-w-0" style={{ height: TABLE_HEIGHT }}>
                  <RankingTop5Table
                    data={estadisticas?.rankingTop5}
                    loading={estadisticasFase === "cargando"}
                    error={estadisticasError}
                  />
                </div>

                {/* Series reales de DASHBOARD_WEB (regionales/dependencias/resultados). */}
                <EstadisticasSection rango={comparisonPeriod} />
              </div>
            ) : null}

            {activeTab === "hospitales" ? <HospitalDashboard /> : null}

            {activeTab === "comparativas" ? (
              <div className="min-w-0" style={{ height: TABLE_HEIGHT }}>
                {estadisticasFase === "cargando" ? (
                  <TableSkeleton />
                ) : estadisticasFase === "error" ? (
                  <p
                    role="alert"
                    className="panel flex h-full items-center justify-center text-sm text-neg"
                  >
                    No se pudieron cargar las comparativas.{" "}
                    {estadisticasError ?? "Error desconocido."}
                  </p>
                ) : gruposComparativas.length > 0 ? (
                  <TurnosColumnsChart
                    mode="unidad"
                    title="Consultas por mes (dato real)"
                    testId="chart-comparativas-mensual"
                    groups={gruposComparativas}
                  />
                ) : (
                  <p
                    role="status"
                    className="panel flex h-full items-center justify-center text-sm text-muted"
                  >
                    SIN DATOS
                  </p>
                )}
              </div>
            ) : null}
          </main>
        </div>
      </div>
    </>
  );
}
