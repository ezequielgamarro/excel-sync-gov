/**
 * Pantalla principal (panel de administración táctico): sidebar fijo + cabecera
 * + contenido scrolleable. El documento no scrollea; el scroll vive en el `main`.
 *
 * Datos:
 * - Resumen y Comparativas: snapshot (`indicators.snapshot`).
 * - Incidentes/Logística/Estadísticas: fuente Supabase
 *   (`intervenciones_diarias`) vía `useIntervenciones`, derivada a
 *   `EstadisticasRespuesta`. Sin datos → estado vacío, nunca demo.
 */

import { useEffect, useState } from "react";
import type { CSSProperties, ReactNode } from "react";
import { motion } from "framer-motion";
import type { AuthSession } from "../auth/session";
import { useDashboard } from "../hooks/useDashboard";
import { TABLERO_KPI_LABEL, TABLERO_KPI_ORDER } from "../types";
import type {
  ConsultaGroup,
  EstadisticaItem,
  IncidenteFecha,
  Kpi,
  KpiDirection,
  TableroCpiKey,
} from "../types";
import { Header } from "../components/Header";
import { KpiCard } from "../components/KpiCard";
import { KpiSkeleton } from "../components/Skeletons";
import {
  InvalidDataBanner,
  PartialDataNotice,
  SchemaErrorBanner,
  StaleBanner,
} from "../components/Banners";
import { ADMIN_SECTIONS, AdminSidebar, EXTRA_SECTIONS } from "../components/layout/AdminSidebar";
import { UsuariosAdmin } from "../components/usuarios/UsuariosAdmin";
import { AuditoriaEventos } from "../components/auditoria/AuditoriaEventos";
import { EmpleadosProductividad } from "../components/empleados/EmpleadosProductividad";
import { rolDeSesion, seccionInicial, seccionPermitida, SECCIONES_POR_ROL } from "../auth/roles";
import { HelpScreen } from "./HelpScreen";
import { FormularioCarga } from "../components/intervenciones/FormularioCarga";
import { HistorialRegistros } from "../components/intervenciones/HistorialRegistros";
import { COMPARISON_LABEL } from "../lib/comparison";
import { aSerie } from "../lib/estadisticas";
import { formatInteger } from "../lib/format";
import { useComparison } from "../state/ComparisonContext";
import { useFilters } from "../state/FiltersContext";
import { RealtimeEventsChart } from "../components/charts/RealtimeEventsChart";
import { TurnosColumnsChart } from "../components/charts/TurnosColumnsChart";
import { DistributionDonutChart } from "../components/charts/DistributionDonutChart";
import { EvolucionDiariaChart } from "../components/charts/EvolucionDiariaChart";
import { BarrasHorizontalesChart } from "../components/charts/BarrasHorizontalesChart";
import { EstadisticasSection } from "../components/estadisticas/EstadisticasSection";
import { Comparativas } from "../components/estadisticas/Comparativas";
import { KpiResumenCharts } from "../components/estadisticas/KpiResumenCharts";
import { RankingTop5Table } from "../components/estadisticas/RankingTop5Table";
import { useIntervenciones } from "../hooks/useIntervenciones";
import { usePrefersReducedMotion } from "../hooks/useAnimatedNumber";

export interface DashboardScreenProps {
  session: AuthSession | null;
  onLogout: () => void;
}

const CHART_HEIGHT = 340;

/** Adapta una serie `{name, value}` a la forma `ConsultaGroup` de los gráficos. */
function aGrupos(items?: EstadisticaItem[] | null): ConsultaGroup[] {
  return (items ?? []).map((item) => ({
    key: item.name,
    label: item.name,
    value: item.value,
    positivos: item.positivos,
  }));
}

/** Bloque de contenido con entrada suave (opacidad + desplazamiento vertical). */
function FadeInBlock({
  children,
  className,
  style,
}: {
  children: ReactNode;
  className?: string;
  style?: CSSProperties;
}): JSX.Element {
  return (
    <motion.div
      className={className}
      style={style}
      initial={{ opacity: 0, scale: 0.95, y: 10 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      transition={{ duration: 0.6 }}
    >
      {children}
    </motion.div>
  );
}

/** Mapa sección ↔ hash de URL (sin React Router). */
const HASH_BY_ID: Record<string, string> = {
  resumen: "#/resumen",
  incidentes: "#/incidentes",
  carga: "#/carga",
  historial: "#/historial",
  logistica: "#/logistica",
  estadisticas: "#/estadisticas",
  comparativas: "#/comparativas",
  monitor: "#/monitor",
  usuarios: "#/usuarios",
  auditoria: "#/auditoria",
  empleados: "#/empleados",
  ayuda: "#/ayuda",
};

const ID_BY_HASH: Record<string, string> = Object.fromEntries(
  Object.entries(HASH_BY_ID).map(([id, hash]) => [hash, id]),
);

export function DashboardScreen({ session, onLogout }: DashboardScreenProps): JSX.Element {
  const { state, stale, now, lastSyncAt } = useDashboard(true);
  const rol = rolDeSesion(session);
  const [activeTabRaw, setActiveTab] = useState<string>(
    () => ID_BY_HASH[window.location.hash] ?? seccionInicial(rol),
  );
  // Un rol nunca ve una sección que no le corresponde (aunque cambie el hash).
  const activeTab = seccionPermitida(rol, activeTabRaw) ? activeTabRaw : seccionInicial(rol);
  const seccionesMenu = SECCIONES_POR_ROL[rol]
    .map((id) => [...ADMIN_SECTIONS, ...EXTRA_SECTIONS].find((section) => section.id === id))
    .filter((section): section is NonNullable<typeof section> => section !== undefined);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const { filters, setUnidadesDisponibles } = useFilters();

  const reducedMotion = usePrefersReducedMotion();

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
  const { period: comparisonPeriod } = useComparison();
  const filtroKey = `${String(filters.unidad)}|${filters.rango}|${comparisonPeriod}`;

  const snapshot = state.snapshot;
  const tz = snapshot?.tz ?? "America/Argentina/Buenos_Aires";
  const ageSeconds = Math.max(0, (now - lastSyncAt) / 1000);

  // Datos reales derivados de Supabase (`intervenciones_diarias`) para
  // Incidentes, Logística, Estadísticas y Comparativas.
  const {
    datos: charts,
    fase: chartsFase,
    error: chartsError,
    refetch: chartsRefetch,
  } = useIntervenciones({
    unidad: String(filters.unidad),
    rango: filters.rango,
    period: comparisonPeriod,
  });

  // Selector de Unidad Regional DINÁMICO: catálogo real derivado de Supabase.
  useEffect(() => {
    setUnidadesDisponibles(charts?.regionales_disponibles ?? []);
  }, [charts?.regionales_disponibles, setUnidadesDisponibles]);

  // Estados derivados para todos los gráficos (skeletons en `"cargando"`).
  const chartsLoading = chartsFase === "cargando";

  // Serie HORARIA para el «Flujo de Eventos en Tiempo Real» (buckets `HH:00`).
  const seriesHoraria = aSerie(charts?.incidentes_por_hora);

  const gruposUnidadFinal = aGrupos(
    charts?.intervenciones_por_unidad ?? charts?.grafico_regionales,
  );

  const serieDiaria: IncidenteFecha[] = charts?.incidentes_por_fecha ?? [];

  const gruposTipoFinal = aGrupos(
    charts?.distribucion_incidentes ?? charts?.incidentes_por_tipo,
  );

  const consultasVehiculosLogistica = charts?.totales?.consultas_vehiculos ?? null;
  const consultasArmasLogistica = charts?.totales?.consultas_armas ?? null;
  const hayLogistica = consultasVehiculosLogistica !== null || consultasArmasLogistica !== null;

  // KPIs SUPERIORES conectados a los TOTALES REALES de las intervenciones (sin
  // semillas), derivados de Supabase: `charts?.totales` y su baseline.
  const totalesActuales = charts?.totales;
  const totalesPrevios = charts?.totales_previos;

  const valoresKpi: Record<TableroCpiKey, number> = {
    total_intervenciones: totalesActuales?.total_intervenciones ?? 0,
    total_positivos: totalesActuales?.total_positivos ?? 0,
    consultas_personas: totalesActuales?.consultas_personas ?? 0,
    consultas_vehiculos: totalesActuales?.consultas_vehiculos ?? 0,
    consultas_armas: totalesActuales?.consultas_armas ?? 0,
    consultas_elementos: totalesActuales?.consultas_elementos ?? 0,
  };

  // Bases del período de comparación inmediatamente anterior (si Supabase
  // pudo derivarlas). Sin referencia real, la tarjeta muestra «— sin período».
  const basesPrevias: Record<TableroCpiKey, number | undefined> = {
    total_intervenciones: totalesPrevios?.total_intervenciones,
    total_positivos: totalesPrevios?.total_positivos,
    consultas_personas: totalesPrevios?.consultas_personas,
    consultas_vehiculos: totalesPrevios?.consultas_vehiculos,
    consultas_armas: totalesPrevios?.consultas_armas,
    consultas_elementos: totalesPrevios?.consultas_elementos,
  };

  const kpiReal = (key: TableroCpiKey): Kpi => {
    const value = valoresKpi[key];
    const label = TABLERO_KPI_LABEL[key];

    // NUNCA «N/A»: sin baseline válido (> 0 y finito) no hay referencia y la
    // tarjeta muestra «— sin {período}» en vez de un chip.
    const base = basesPrevias[key];
    const hasBase = typeof base === "number" && Number.isFinite(base) && base > 0;

    if (!hasBase) {
      return {
        label,
        value,
        delta_abs: null,
        delta_pct: null,
        direction: "flat",
        comparison: "ayer_mismo_tramo",
        baseline_value: 0,
        as_of: "",
        has_reference: false,
      };
    }

    const deltaAbs: number = value - base;
    const deltaPct: number | null = ((value - base) / base) * 100;
    const direction: KpiDirection = deltaAbs > 0 ? "up" : deltaAbs < 0 ? "down" : "flat";

    return {
      label,
      value,
      delta_abs: deltaAbs,
      delta_pct: deltaPct,
      direction,
      comparison: "ayer_mismo_tramo",
      baseline_value: base,
      as_of: "",
      has_reference: true,
    };
  };

  const kpiRow = (
    <motion.div
      className="grid gap-[var(--grid-gutter)] grid-cols-[repeat(auto-fit,minmax(min(100%,240px),1fr))]"
      variants={{ hidden: {}, show: { transition: { staggerChildren: reducedMotion ? 0 : 0.12 } } }}
      initial="hidden"
      animate="show"
    >
      {chartsFase === "cargando"
        ? TABLERO_KPI_ORDER.map((key) => (
            <motion.div
              key={key}
              className="min-w-0"
              variants={
                reducedMotion
                  ? { hidden: { opacity: 0 }, show: { opacity: 1, transition: { duration: 0.3 } } }
                  : {
                      hidden: { opacity: 0, y: 20 },
                      show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: "easeOut" } },
                    }
              }
            >
              <KpiSkeleton />
            </motion.div>
          ))
        : TABLERO_KPI_ORDER.map((key) => (
            <motion.div
              key={key}
              className="min-w-0"
              variants={
                reducedMotion
                  ? { hidden: { opacity: 0 }, show: { opacity: 1, transition: { duration: 0.3 } } }
                  : {
                      hidden: { opacity: 0, y: 20 },
                      show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: "easeOut" } },
                    }
              }
            >
              <KpiCard
                kpiKey={key}
                kpi={kpiReal(key)}
                periodLabel={COMPARISON_LABEL[comparisonPeriod]}
                dimmed={stale}
              />
            </motion.div>
          ))}
    </motion.div>
  );

  return (
    <>
      <a className="skip-link" href="#contenido">
        Saltar al contenido
      </a>
      <div className="admin-shell flex overflow-hidden">
        {/* El visitante no tiene menú lateral: solo ve el monitor. */}
        {rol !== "visitante" ? (
          <AdminSidebar
            activeTab={activeTab}
            sections={seccionesMenu}
            onSelect={selectTab}
            open={sidebarOpen}
            onClose={() => setSidebarOpen(false)}
          />
        ) : null}

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
            onOpenSidebar={rol !== "visitante" ? () => setSidebarOpen(true) : undefined}
            sidebarOpen={sidebarOpen}
            rol={rol}
            mostrarFiltros={rol !== "empleado" || activeTab === "monitor"}
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

                {/* Series reales de la hoja DASHBOARD_WEB (sin datos demo). */}
                <EstadisticasSection
                  datos={charts}
                  fase={chartsFase}
                  error={chartsError}
                  refetch={chartsRefetch}
                />

                {/* Gráficos reales derivados de Supabase (sin semillas). */}
                <div className="grid grid-cols-1 gap-[var(--grid-gutter)] xl:grid-cols-2">
                  <FadeInBlock
                    className="grid min-w-0 xl:col-span-2"
                    style={{ minHeight: CHART_HEIGHT }}
                  >
                    <EvolucionDiariaChart
                      key={`${filtroKey}-evolucion-resumen`}
                      data={serieDiaria}
                      loading={chartsLoading}
                      error={chartsError}
                    />
                  </FadeInBlock>
                  <FadeInBlock className="grid min-w-0 xl:col-span-2" style={{ minHeight: CHART_HEIGHT }}>
                    <TurnosColumnsChart
                      key={`${filtroKey}-unidad-resumen`}
                      mode="unidad"
                      title="Intervenciones por Unidad Regional"
                      testId="chart-columns-unidad"
                      groups={gruposUnidadFinal}
                      loading={chartsLoading}
                      error={chartsError}
                    />
                  </FadeInBlock>
                </div>

                {/* Ranking Top 5 REAL (datos.rankingTop5; sin ranking semilla). */}
                <div className="flex flex-col gap-[var(--grid-gutter)]">
                  <FadeInBlock className="grid min-w-0">
                    {snapshot?.payload.quality.partial ? <PartialDataNotice /> : null}
                    <RankingTop5Table
                      key={`${filtroKey}-ranking-resumen`}
                      data={charts?.rankingTop5}
                      loading={chartsFase === "cargando"}
                      error={chartsError}
                      rango={filters.rango}
                      period={comparisonPeriod}
                    />
                  </FadeInBlock>
                </div>
              </div>
            ) : null}

            {activeTab === "incidentes" ? (
              <div className="grid grid-cols-1 gap-[var(--grid-gutter)]">
                <FadeInBlock className="grid min-w-0" style={{ minHeight: 380 }}>
                  <RealtimeEventsChart
                    key={`${filtroKey}-realtime-incidentes`}
                    series={seriesHoraria}
                    flujo={charts?.flujo}
                    loading={chartsLoading}
                    error={chartsError}
                  />
                </FadeInBlock>
                <FadeInBlock className="grid min-w-0" style={{ minHeight: 320 }}>
                  <EvolucionDiariaChart
                    key={`${filtroKey}-evolucion-incidentes`}
                    data={serieDiaria}
                    loading={chartsLoading}
                    error={chartsError}
                  />
                </FadeInBlock>
              </div>
            ) : null}

            {activeTab === "logistica" ? (
              <div className="flex flex-col gap-[var(--grid-gutter)]">
                {hayLogistica ? (
                  <div className="panel flex flex-wrap items-center gap-6 py-3">
                    <span className="flex items-baseline gap-2">
                      <span className="text-[11px] uppercase tracking-wide text-muted">
                        Consultas de Vehículos
                      </span>
                      <span className="num text-xl font-semibold text-ink">
                        {formatInteger(consultasVehiculosLogistica ?? 0)}
                      </span>
                    </span>
                    <span className="flex items-baseline gap-2">
                      <span className="text-[11px] uppercase tracking-wide text-muted">
                        Consultas de Armas
                      </span>
                      <span className="num text-xl font-semibold text-ink">
                        {formatInteger(consultasArmasLogistica ?? 0)}
                      </span>
                    </span>
                  </div>
                ) : null}
                {/* Logística REAL: barras HORIZONTALES por Unidad Regional. */}
                <FadeInBlock className="min-w-0">
                  <BarrasHorizontalesChart
                    key={`${filtroKey}-vehiculos-logistica`}
                    title="Vehículos Secuestrados por Regional"
                    testId="chart-logistica-vehiculos"
                    data={
                      charts?.vehiculosPorRegional ??
                      charts?.logistica_vehiculos_por_regional
                    }
                    loading={chartsLoading}
                    error={chartsError}
                  />
                </FadeInBlock>
                <FadeInBlock className="min-w-0">
                  <BarrasHorizontalesChart
                    key={`${filtroKey}-armas-logistica`}
                    title="Armas Secuestradas por Regional"
                    testId="chart-logistica-armas"
                    data={
                      charts?.armasPorRegional ?? charts?.logistica_armas_por_regional
                    }
                    loading={chartsLoading}
                    error={chartsError}
                  />
                </FadeInBlock>
                <FadeInBlock key={`${filtroKey}-aprehendidos-logistica`} className="min-w-0">
                  <BarrasHorizontalesChart
                    title="Personas Aprehendidas por Regional"
                    testId="chart-logistica-aprehendidos"
                    data={charts?.aprehendidosPorRegional ?? []}
                    loading={chartsLoading}
                    error={chartsError}
                  />
                </FadeInBlock>

                {/* Desglose por subtipo: vehículos, armas y personas. */}
                <div className="grid grid-cols-1 gap-[var(--grid-gutter)] xl:grid-cols-3">
                  <FadeInBlock key={`${filtroKey}-vehiculos-tipo`} className="min-w-0">
                    <BarrasHorizontalesChart
                      title="Vehículos por Tipo"
                      testId="chart-logistica-vehiculos-tipo"
                      data={charts?.vehiculosPorTipo ?? []}
                      loading={chartsLoading}
                      error={chartsError}
                    />
                  </FadeInBlock>
                  <FadeInBlock key={`${filtroKey}-armas-tipo`} className="min-w-0">
                    <BarrasHorizontalesChart
                      title="Armas por Tipo"
                      testId="chart-logistica-armas-tipo"
                      data={charts?.armasPorTipo ?? []}
                      loading={chartsLoading}
                      error={chartsError}
                    />
                  </FadeInBlock>
                  <FadeInBlock key={`${filtroKey}-personas-causa`} className="min-w-0">
                    <BarrasHorizontalesChart
                      title="Personas por Causa"
                      testId="chart-logistica-personas-causa"
                      data={charts?.personasPorCausa ?? []}
                      loading={chartsLoading}
                      error={chartsError}
                    />
                  </FadeInBlock>
                </div>
              </div>
            ) : null}

            {activeTab === "estadisticas" ? (
              <div className="flex flex-col gap-[var(--grid-gutter)]">
                <div className="grid grid-cols-1 gap-[var(--grid-gutter)] xl:grid-cols-2 2xl:grid-cols-3">
                  <FadeInBlock
                    className="grid min-w-0 xl:col-span-2 2xl:col-span-3"
                    style={{ minHeight: CHART_HEIGHT }}
                  >
                    <EvolucionDiariaChart
                      key={`${filtroKey}-evolucion-estadisticas`}
                      data={serieDiaria}
                      loading={chartsLoading}
                      error={chartsError}
                    />
                  </FadeInBlock>
                  <FadeInBlock className="grid min-w-0 xl:col-span-2 2xl:col-span-3" style={{ minHeight: CHART_HEIGHT }}>
                    <TurnosColumnsChart
                      key={`${filtroKey}-unidad-estadisticas`}
                      mode="unidad"
                      title="Intervenciones por Unidad Regional"
                      testId="chart-columns-unidad"
                      groups={gruposUnidadFinal}
                      loading={chartsLoading}
                      error={chartsError}
                    />
                  </FadeInBlock>
                  <FadeInBlock className="grid min-w-0" style={{ minHeight: CHART_HEIGHT }}>
                    <DistributionDonutChart
                      key={`${filtroKey}-distribucion-estadisticas`}
                      title="Distribución por Tipo"
                      groups={gruposTipoFinal}
                      loading={chartsLoading}
                      error={chartsError}
                    />
                  </FadeInBlock>
                  <FadeInBlock className="grid min-w-0" style={{ minHeight: CHART_HEIGHT }}>
                    <RealtimeEventsChart
                      key={`${filtroKey}-realtime-estadisticas`}
                      series={seriesHoraria}
                      flujo={charts?.flujo}
                      loading={chartsLoading}
                      error={chartsError}
                    />
                  </FadeInBlock>
                  <FadeInBlock className="min-w-0">
                    <BarrasHorizontalesChart
                      key={`${filtroKey}-vehiculos-estadisticas`}
                      title="Vehículos Secuestrados por Regional"
                      testId="chart-logistica-vehiculos"
                      data={
                        charts?.vehiculosPorRegional ??
                        charts?.logistica_vehiculos_por_regional
                      }
                      loading={chartsLoading}
                      error={chartsError}
                    />
                  </FadeInBlock>
                  <FadeInBlock className="min-w-0">
                    <BarrasHorizontalesChart
                      key={`${filtroKey}-armas-estadisticas`}
                      title="Armas Secuestradas por Regional"
                      testId="chart-logistica-armas"
                      data={
                        charts?.armasPorRegional ?? charts?.logistica_armas_por_regional
                      }
                      loading={chartsLoading}
                      error={chartsError}
                    />
                  </FadeInBlock>
                </div>

                <FadeInBlock className="grid min-w-0">
                  <RankingTop5Table
                    key={`${filtroKey}-ranking-estadisticas`}
                    data={charts?.rankingTop5}
                    loading={chartsFase === "cargando"}
                    error={chartsError}
                    rango={filters.rango}
                    period={comparisonPeriod}
                  />
                </FadeInBlock>

                {/* Series reales de DASHBOARD_WEB (regionales/dependencias/resultados). */}
                <EstadisticasSection
                  datos={charts}
                  fase={chartsFase}
                  error={chartsError}
                  refetch={chartsRefetch}
                />
              </div>
            ) : null}

            {activeTab === "auditoria" && rol === "admin" ? <AuditoriaEventos /> : null}

            {activeTab === "empleados" && rol === "admin" ? <EmpleadosProductividad /> : null}

            {activeTab === "usuarios" && rol === "admin" ? (
              <UsuariosAdmin miId={session?.sub ?? ""} />
            ) : null}

            {activeTab === "monitor" ? (
              <div className="flex flex-col gap-6" data-testid="vista-monitor">
                {kpiRow}

                <EstadisticasSection
                  datos={charts}
                  fase={chartsFase}
                  error={chartsError}
                  refetch={chartsRefetch}
                />

                <KpiResumenCharts
                  totales={charts?.totales}
                  totalesPrevios={charts?.totales_previos}
                  loading={chartsLoading}
                  error={chartsError}
                />

                <FadeInBlock className="grid min-w-0" style={{ minHeight: CHART_HEIGHT }}>
                  <EvolucionDiariaChart
                    key={`${filtroKey}-evolucion-monitor`}
                    data={serieDiaria}
                    loading={chartsLoading}
                    error={chartsError}
                  />
                </FadeInBlock>
                <FadeInBlock className="grid min-w-0" style={{ minHeight: CHART_HEIGHT }}>
                  <TurnosColumnsChart
                    key={`${filtroKey}-unidad-monitor`}
                    mode="unidad"
                    title="Intervenciones por Unidad Regional"
                    testId="chart-columns-unidad"
                    groups={gruposUnidadFinal}
                    loading={chartsLoading}
                    error={chartsError}
                  />
                </FadeInBlock>

                <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,420px),1fr))] gap-[var(--grid-gutter)]">
                  <FadeInBlock className="grid min-w-0" style={{ minHeight: CHART_HEIGHT }}>
                    <DistributionDonutChart
                      key={`${filtroKey}-distribucion-monitor`}
                      title="Distribución por Tipo"
                      groups={gruposTipoFinal}
                      loading={chartsLoading}
                      error={chartsError}
                    />
                  </FadeInBlock>
                  <FadeInBlock className="grid min-w-0" style={{ minHeight: CHART_HEIGHT }}>
                    <RealtimeEventsChart
                      key={`${filtroKey}-realtime-monitor`}
                      series={seriesHoraria}
                      flujo={charts?.flujo}
                      loading={chartsLoading}
                      error={chartsError}
                    />
                  </FadeInBlock>
                </div>

                <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,420px),1fr))] gap-[var(--grid-gutter)]">
                  <FadeInBlock className="min-w-0">
                    <BarrasHorizontalesChart
                      key={`${filtroKey}-vehiculos-monitor`}
                      title="Vehículos Secuestrados por Regional"
                      testId="chart-logistica-vehiculos"
                      data={
                        charts?.vehiculosPorRegional ??
                        charts?.logistica_vehiculos_por_regional
                      }
                      loading={chartsLoading}
                      error={chartsError}
                    />
                  </FadeInBlock>
                  <FadeInBlock className="min-w-0">
                    <BarrasHorizontalesChart
                      key={`${filtroKey}-armas-monitor`}
                      title="Armas Secuestradas por Regional"
                      testId="chart-logistica-armas"
                      data={
                        charts?.armasPorRegional ?? charts?.logistica_armas_por_regional
                      }
                      loading={chartsLoading}
                      error={chartsError}
                    />
                  </FadeInBlock>
                  <FadeInBlock className="min-w-0">
                    <BarrasHorizontalesChart
                      key={`${filtroKey}-aprehendidos-monitor`}
                      title="Personas Aprehendidas por Regional"
                      testId="chart-logistica-aprehendidos"
                      data={charts?.aprehendidosPorRegional ?? []}
                      loading={chartsLoading}
                      error={chartsError}
                    />
                  </FadeInBlock>
                </div>

                <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,360px),1fr))] gap-[var(--grid-gutter)]">
                  <FadeInBlock className="min-w-0">
                    <BarrasHorizontalesChart
                      key={`${filtroKey}-vehiculos-tipo-monitor`}
                      title="Vehículos por Tipo"
                      testId="chart-logistica-vehiculos-tipo"
                      data={charts?.vehiculosPorTipo ?? []}
                      loading={chartsLoading}
                      error={chartsError}
                    />
                  </FadeInBlock>
                  <FadeInBlock className="min-w-0">
                    <BarrasHorizontalesChart
                      key={`${filtroKey}-armas-tipo-monitor`}
                      title="Armas por Tipo"
                      testId="chart-logistica-armas-tipo"
                      data={charts?.armasPorTipo ?? []}
                      loading={chartsLoading}
                      error={chartsError}
                    />
                  </FadeInBlock>
                  <FadeInBlock className="min-w-0">
                    <BarrasHorizontalesChart
                      key={`${filtroKey}-personas-causa-monitor`}
                      title="Personas por Causa"
                      testId="chart-logistica-personas-causa"
                      data={charts?.personasPorCausa ?? []}
                      loading={chartsLoading}
                      error={chartsError}
                    />
                  </FadeInBlock>
                </div>

                <FadeInBlock className="grid min-w-0">
                  <RankingTop5Table
                    key={`${filtroKey}-ranking-monitor`}
                    data={charts?.rankingTop5}
                    loading={chartsFase === "cargando"}
                    error={chartsError}
                    rango={filters.rango}
                    period={comparisonPeriod}
                  />
                </FadeInBlock>

                <Comparativas
                  datos={charts}
                  fase={chartsFase}
                  error={chartsError}
                  refetch={chartsRefetch}
                  period={comparisonPeriod}
                />
              </div>
            ) : null}

            {activeTab === "carga" ? <FormularioCarga /> : null}

            {activeTab === "historial" ? <HistorialRegistros /> : null}

            {activeTab === "comparativas" ? (
              <div className="flex flex-col gap-6">
                {/* Mismas tarjetas KPI del Resumen General. */}
                {kpiRow}
                {/* Los KPIs del Resumen General, en gráficos. */}
                <KpiResumenCharts
                  totales={charts?.totales}
                  totalesPrevios={charts?.totales_previos}
                  loading={chartsLoading}
                  error={chartsError}
                />
                <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,360px),1fr))] gap-[var(--grid-gutter)]">
                  <FadeInBlock className="grid min-w-0" style={{ minHeight: CHART_HEIGHT }}>
                    <TurnosColumnsChart
                      key={`${filtroKey}-unidad-cisop`}
                      mode="unidad"
                      title="Intervenciones por Unidad Regional"
                      testId="chart-columns-unidad"
                      groups={gruposUnidadFinal}
                      loading={chartsLoading}
                      error={chartsError}
                    />
                  </FadeInBlock>
                </div>
                <FadeInBlock className="grid min-w-0" style={{ minHeight: CHART_HEIGHT }}>
                  <EvolucionDiariaChart
                    key={`${filtroKey}-evolucion-cisop`}
                    data={serieDiaria}
                    loading={chartsLoading}
                    error={chartsError}
                  />
                </FadeInBlock>
                <Comparativas
                  datos={charts}
                  fase={chartsFase}
                  error={chartsError}
                  refetch={chartsRefetch}
                  period={comparisonPeriod}
                />
              </div>
            ) : null}
          </main>
        </div>
      </div>
    </>
  );
}
