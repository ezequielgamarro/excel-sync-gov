/**
 * Ventana «Imprimir / PDF»: el usuario elige el rango de fechas y qué gráficos
 * incluir; se arma una hoja de informe con los datos de ESE rango y se imprime
 * (en el diálogo del navegador se puede elegir «Guardar como PDF»).
 *
 * Los datos se leen de Supabase (`intervenciones_diarias`) y se derivan con la
 * misma lógica del dashboard (`derivarEstadisticas`), pero con una ventana
 * propia (`ventanaDias`) en lugar de los filtros globales.
 */

import { useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { createPortal } from "react-dom";
import { Printer, X } from "lucide-react";
import { supabase } from "../../supabaseClient";
import { recolectarTodas } from "../../data/api";
import type { Intervencion } from "../../data/api";
import { derivarEstadisticas } from "../../lib/intervenciones";
import type { IntervencionesDerivadas } from "../../lib/intervenciones";
import { aGrupos, aSerie } from "../../lib/estadisticas";
import { mensajeDeError, registrarEvento } from "../../lib/auditoria";
import { EstadisticasKpis } from "../estadisticas/EstadisticasKpis";
import { EvolucionDiariaChart } from "../charts/EvolucionDiariaChart";
import { RealtimeEventsChart } from "../charts/RealtimeEventsChart";
import { TurnosColumnsChart } from "../charts/TurnosColumnsChart";
import { DistributionDonutChart } from "../charts/DistributionDonutChart";
import { BarrasHorizontalesChart } from "../charts/BarrasHorizontalesChart";
import { RegionalesBarChart } from "../estadisticas/RegionalesBarChart";
import { DependenciasBarChart } from "../estadisticas/DependenciasBarChart";
import { ResultadosDonutChart } from "../estadisticas/ResultadosDonutChart";
import { RankingTop5Table } from "../estadisticas/RankingTop5Table";

const MS_DIA = 86_400_000;
const ALTO_GRAFICO = 340;
const ALTO_FILA = 38;

function isoLocal(date: Date): string {
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function desdeIso(iso: string): Date {
  const [y, m, d] = iso.split("-").map(Number);
  return new Date(y, m - 1, d);
}

function sumarDias(iso: string, dias: number): string {
  return isoLocal(new Date(desdeIso(iso).getTime() + dias * MS_DIA));
}

function diasEntre(desde: string, hasta: string): number {
  return Math.round((desdeIso(hasta).getTime() - desdeIso(desde).getTime()) / MS_DIA) + 1;
}

function formatoFecha(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `${d}/${m}/${y}`;
}

interface Bloque {
  id: string;
  label: string;
  /** Ocupa todo el ancho de la hoja (si no, media hoja). */
  completo: boolean;
  render: (d: IntervencionesDerivadas) => ReactNode;
}

function enAltura(alto: number, hijo: ReactNode): ReactNode {
  return <div style={{ height: alto }}>{hijo}</div>;
}

const BLOQUES: readonly Bloque[] = [
  {
    id: "kpis",
    label: "Totales (tarjetas KPI)",
    completo: true,
    render: (d) => <EstadisticasKpis totales={d.totales} kpis={d.kpis} />,
  },
  {
    id: "evolucion",
    label: "Evolución diaria",
    completo: true,
    render: (d) => enAltura(ALTO_GRAFICO, <EvolucionDiariaChart data={d.incidentes_por_fecha} />),
  },
  {
    id: "flujo",
    label: "Flujo de consultas",
    completo: true,
    render: (d) =>
      enAltura(
        ALTO_GRAFICO,
        <RealtimeEventsChart series={aSerie(d.incidentes_por_hora)} flujo={d.flujo} />,
      ),
  },
  {
    id: "unidad_columnas",
    label: "Intervenciones por Unidad Regional (columnas)",
    completo: true,
    render: (d) =>
      enAltura(
        ALTO_GRAFICO,
        <TurnosColumnsChart
          mode="unidad"
          title="Intervenciones por Unidad Regional"
          testId="informe-unidad-columnas"
          groups={aGrupos(d.intervenciones_por_unidad ?? d.grafico_regionales)}
        />,
      ),
  },
  {
    id: "unidad_barras",
    label: "Intervenciones por Unidad Regional (barras)",
    completo: true,
    render: (d) => {
      const datos = d.grafico_regionales ?? [];
      return enAltura(
        Math.max(ALTO_GRAFICO, datos.length * ALTO_FILA + 90),
        <RegionalesBarChart data={datos} />,
      );
    },
  },
  {
    id: "direcciones",
    label: "Intervenciones por Dirección",
    completo: true,
    render: (d) => {
      const datos = d.grafico_dependencias ?? [];
      return enAltura(
        Math.max(ALTO_GRAFICO, datos.length * ALTO_FILA + 90),
        <DependenciasBarChart data={datos} />,
      );
    },
  },
  {
    id: "tipo",
    label: "Distribución por tipo de consulta",
    completo: false,
    render: (d) =>
      enAltura(
        ALTO_GRAFICO,
        <DistributionDonutChart
          title="Distribución por Tipo"
          groups={aGrupos(d.distribucion_incidentes ?? d.incidentes_por_tipo)}
        />,
      ),
  },
  {
    id: "resultados",
    label: "Sistema utilizado",
    completo: false,
    render: (d) => enAltura(ALTO_GRAFICO, <ResultadosDonutChart data={d.alertas_resultados ?? []} />),
  },
  {
    id: "vehiculos",
    label: "Vehículos secuestrados por regional",
    completo: false,
    render: (d) => (
      <BarrasHorizontalesChart
        title="Vehículos Secuestrados por Regional"
        data={d.vehiculosPorRegional ?? d.logistica_vehiculos_por_regional}
      />
    ),
  },
  {
    id: "armas",
    label: "Armas secuestradas por regional",
    completo: false,
    render: (d) => (
      <BarrasHorizontalesChart
        title="Armas Secuestradas por Regional"
        data={d.armasPorRegional ?? d.logistica_armas_por_regional}
      />
    ),
  },
  {
    id: "aprehendidos",
    label: "Personas aprehendidas por regional",
    completo: false,
    render: (d) => (
      <BarrasHorizontalesChart
        title="Personas Aprehendidas por Regional"
        data={d.aprehendidosPorRegional ?? []}
      />
    ),
  },
  {
    id: "vehiculos_tipo",
    label: "Vehículos por tipo",
    completo: false,
    render: (d) => <BarrasHorizontalesChart title="Vehículos por Tipo" data={d.vehiculosPorTipo ?? []} />,
  },
  {
    id: "armas_tipo",
    label: "Armas por tipo",
    completo: false,
    render: (d) => <BarrasHorizontalesChart title="Armas por Tipo" data={d.armasPorTipo ?? []} />,
  },
  {
    id: "personas_causa",
    label: "Personas por causa",
    completo: false,
    render: (d) => (
      <BarrasHorizontalesChart title="Personas por Causa" data={d.personasPorCausa ?? []} />
    ),
  },
  {
    id: "ranking",
    label: "Ranking de dependencias",
    completo: true,
    render: (d) => <RankingTop5Table data={d.rankingTop5} />,
  },
];

const INPUT_CLASS =
  "touch-target rounded-[10px] border border-border bg-surface2 px-3 text-sm normal-case text-ink transition-colors focus-visible:border-accent";

const CHIP_CLASS =
  "touch-target rounded-[10px] border border-border bg-surface2 px-3 text-xs font-semibold text-ink2 transition-colors hover:border-accent hover:text-accent";

export interface InformeImpresionProps {
  onClose: () => void;
}

export function InformeImpresion({ onClose }: InformeImpresionProps): JSX.Element {
  const hoy = isoLocal(new Date());
  const [desde, setDesde] = useState(() => sumarDias(hoy, -29));
  const [hasta, setHasta] = useState(hoy);
  const [seleccion, setSeleccion] = useState<Set<string>>(() => new Set(BLOQUES.map((b) => b.id)));
  const [datos, setDatos] = useState<IntervencionesDerivadas | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const rangoValido = desde !== "" && hasta !== "" && desde <= hasta;

  // Oculta la app al imprimir (ver `body.informe-abierto` en index.css).
  useEffect(() => {
    document.body.classList.add("informe-abierto");
    return () => document.body.classList.remove("informe-abierto");
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  // Trae el rango pedido más la ventana previa de igual largo (para variaciones).
  useEffect(() => {
    if (!rangoValido) return;
    let cancelado = false;
    setCargando(true);
    setError(null);
    const dias = diasEntre(desde, hasta);
    const desdePrevio = sumarDias(desde, -dias);
    void (async () => {
      try {
        const filas = await recolectarTodas<Intervencion>(() =>
          supabase
            .from("intervenciones_diarias")
            .select("*")
            .gte("fecha_consulta", desdePrevio)
            .lte("fecha_consulta", hasta)
            .order("id", { ascending: true }),
        );
        if (cancelado) return;
        setDatos(derivarEstadisticas(filas, { hoy: desdeIso(hasta), ventanaDias: dias }));
      } catch (err) {
        if (!cancelado) {
          setDatos(null);
          setError(mensajeDeError(err));
        }
      } finally {
        if (!cancelado) setCargando(false);
      }
    })();
    return () => {
      cancelado = true;
    };
  }, [desde, hasta, rangoValido]);

  const elegidos = useMemo(() => BLOQUES.filter((b) => seleccion.has(b.id)), [seleccion]);
  const puedeImprimir = rangoValido && datos !== null && !cargando && elegidos.length > 0;

  const alternar = (id: string): void =>
    setSeleccion((previa) => {
      const siguiente = new Set(previa);
      if (siguiente.has(id)) siguiente.delete(id);
      else siguiente.add(id);
      return siguiente;
    });

  const imprimir = (): void => {
    void registrarEvento("imprimir_pdf", {
      detalle: { desde, hasta, graficos: elegidos.map((b) => b.id) },
    });
    window.print();
  };

  const atajo = (dias: number): void => {
    setHasta(hoy);
    setDesde(sumarDias(hoy, -(dias - 1)));
  };

  return createPortal(
    <div
      id="informe-overlay"
      className="fixed inset-0 z-50 overflow-auto bg-night/90 backdrop-blur-sm"
      role="dialog"
      aria-modal="true"
      aria-label="Imprimir informe"
      data-testid="informe-impresion"
    >
      <div className="flex min-h-full flex-col gap-4 p-4 lg:flex-row">
        <aside
          data-no-print
          className="panel flex w-full shrink-0 flex-col gap-4 lg:sticky lg:top-4 lg:max-h-[calc(100vh-2rem)] lg:w-[340px] lg:self-start lg:overflow-y-auto"
        >
          <div className="flex items-center justify-between gap-3">
            <h3 className="font-display text-lg font-semibold uppercase tracking-wide text-ink">
              Imprimir informe
            </h3>
            <button
              type="button"
              aria-label="Cerrar"
              onClick={onClose}
              className="touch-target inline-flex items-center justify-center rounded-[10px] border border-border bg-surface2 p-2 text-muted transition-colors hover:border-accent hover:text-accent"
            >
              <X size={18} aria-hidden="true" />
            </button>
          </div>

          <fieldset className="flex flex-col gap-3">
            <legend className="mb-1 text-[11px] uppercase tracking-wide text-muted">Período</legend>
            <div className="grid grid-cols-2 gap-3">
              <label className="flex flex-col gap-1 text-[11px] uppercase tracking-wide text-muted">
                Desde
                <input
                  type="date"
                  className={INPUT_CLASS}
                  value={desde}
                  max={hasta || undefined}
                  onChange={(e) => setDesde(e.target.value)}
                />
              </label>
              <label className="flex flex-col gap-1 text-[11px] uppercase tracking-wide text-muted">
                Hasta
                <input
                  type="date"
                  className={INPUT_CLASS}
                  value={hasta}
                  min={desde || undefined}
                  max={hoy}
                  onChange={(e) => setHasta(e.target.value)}
                />
              </label>
            </div>
            <div className="flex flex-wrap gap-2">
              <button type="button" className={CHIP_CLASS} onClick={() => atajo(1)}>
                Hoy
              </button>
              <button type="button" className={CHIP_CLASS} onClick={() => atajo(7)}>
                7 días
              </button>
              <button type="button" className={CHIP_CLASS} onClick={() => atajo(30)}>
                30 días
              </button>
              <button type="button" className={CHIP_CLASS} onClick={() => atajo(365)}>
                1 año
              </button>
            </div>
            {!rangoValido ? (
              <p role="alert" className="text-xs font-semibold text-neg">
                Elegí un rango válido (la fecha inicial no puede superar a la final).
              </p>
            ) : null}
          </fieldset>

          <fieldset className="flex flex-col gap-2">
            <legend className="mb-1 text-[11px] uppercase tracking-wide text-muted">
              Gráficos a imprimir ({elegidos.length}/{BLOQUES.length})
            </legend>
            <div className="flex gap-2">
              <button
                type="button"
                className={CHIP_CLASS}
                onClick={() => setSeleccion(new Set(BLOQUES.map((b) => b.id)))}
              >
                Todos
              </button>
              <button type="button" className={CHIP_CLASS} onClick={() => setSeleccion(new Set())}>
                Ninguno
              </button>
            </div>
            {BLOQUES.map((bloque) => (
              <label key={bloque.id} className="flex items-center gap-2 text-sm text-ink2">
                <input
                  type="checkbox"
                  className="h-4 w-4 accent-[var(--accent)]"
                  checked={seleccion.has(bloque.id)}
                  onChange={() => alternar(bloque.id)}
                />
                {bloque.label}
              </label>
            ))}
          </fieldset>

          <button
            type="button"
            onClick={imprimir}
            disabled={!puedeImprimir}
            className="touch-target inline-flex items-center justify-center gap-2 rounded-[10px] border border-accent/60 bg-accent-soft px-5 text-sm font-semibold uppercase tracking-wide text-accent transition-colors hover:border-accent disabled:cursor-not-allowed disabled:opacity-50"
          >
            <Printer size={16} aria-hidden="true" />
            {cargando ? "Cargando datos…" : "Imprimir / Guardar PDF"}
          </button>
          <p className="text-xs text-muted">
            En la ventana de impresión elegí «Guardar como PDF» si querés el archivo.
          </p>
        </aside>

        <div className="min-w-0 flex-1 overflow-x-auto">
          {error ? (
            <p
              role="alert"
              className="rounded-[12px] border border-neg/50 bg-neg/10 px-4 py-3 text-sm font-semibold text-neg"
            >
              {error}
            </p>
          ) : null}

          <div
            className="informe-hoja mx-auto flex flex-col gap-4 rounded-[12px] border border-border p-6"
            style={{ width: 1000, backgroundColor: "var(--bg-base)" }}
            data-testid="informe-hoja"
          >
            <div className="informe-bloque border-b border-border pb-3">
              <h1 className="font-display text-xl font-semibold uppercase tracking-wide text-ink">
                Informe Operativo Comparativo
              </h1>
              <p className="text-xs uppercase tracking-[0.08em] text-muted">
                Centro Integrador de Sistemas y Operaciones
              </p>
              {rangoValido ? (
                <p className="mt-1 text-sm text-ink2">
                  Período: {formatoFecha(desde)} al {formatoFecha(hasta)} (
                  {diasEntre(desde, hasta)} día{diasEntre(desde, hasta) === 1 ? "" : "s"})
                </p>
              ) : null}
            </div>

            {datos === null && cargando ? (
              <p className="py-10 text-center text-sm text-muted" role="status">
                Cargando datos del período…
              </p>
            ) : null}

            {datos !== null && elegidos.length === 0 ? (
              <p className="py-10 text-center text-sm text-muted" role="status">
                Elegí al menos un gráfico para armar el informe.
              </p>
            ) : null}

            {datos !== null ? (
              <div className="grid grid-cols-2 gap-4">
                {elegidos.map((bloque) => (
                  <div
                    key={bloque.id}
                    className={`informe-bloque min-w-0 ${bloque.completo ? "col-span-2" : ""}`}
                  >
                    {bloque.render(datos)}
                  </div>
                ))}
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </div>,
    document.body,
  );
}
