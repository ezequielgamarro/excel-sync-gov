/**
 * Sección «Estadísticas» (Resumen): series reales derivadas del listado
 * de Supabase (`intervenciones_diarias`).
 *
 * Los KPIs superiores NO se repiten aquí: la fila canónica de 4 tarjetas vive en
 * `DashboardScreen` (conectada a `data.totales`). Esta sección sólo aporta los
 * gráficos reales (regionales, resultados y dependencias).
 *
 * Estados:
 * - `cargando`: skeletons, sin valores.
 * - `error`: panel de error con reintento; NUNCA datos de demostración.
 * - `listo`: barras de regionales/dependencias + dona de resultados.
 *
 * Es una sección PRESENTACIONAL: recibe por props los datos ya filtrados
 * (`datos`), la fase, el error y el `refetch` de `useIntervenciones` desde
 * `DashboardScreen`, de modo que reacciona a los filtros globales (unidad,
 * rango y período de comparación) sin volver a pedir datos.
 */

import type { IntervencionesDerivadas } from "../../lib/intervenciones";
import { Skeleton } from "../Skeletons";
import { RegionalesBarChart } from "./RegionalesBarChart";
import { DependenciasBarChart } from "./DependenciasBarChart";
import { ResultadosDonutChart } from "./ResultadosDonutChart";

const CHART_HEIGHT = 288;
/** Alto (px) reservado por cada fila del gráfico de regionales. */
const FILA_REGIONAL = 38;

function LoadingState(): JSX.Element {
  return (
    <div className="grid grid-cols-1 gap-[var(--grid-gutter)] xl:grid-cols-2">
      {Array.from({ length: 2 }).map((_, index) => (
        <div key={index} className="panel" style={{ height: CHART_HEIGHT }} aria-hidden="true">
          <Skeleton className="mb-6 h-4 w-1/2" />
          <Skeleton className="h-4/5 w-full" />
        </div>
      ))}
    </div>
  );
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }): JSX.Element {
  return (
    <div
      role="alert"
      className="flex flex-wrap items-center gap-3 rounded-[12px] border border-neg/50 bg-surface px-4 py-3 text-sm font-semibold text-neg"
    >
      <span aria-hidden="true">⛔</span>
      <span className="flex-1">
        No se pudieron cargar las estadísticas de la planilla. {message}
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

export interface EstadisticasSectionProps {
  datos: IntervencionesDerivadas | null;
  fase: "cargando" | "listo" | "error";
  error: string | null;
  refetch: () => void;
}

export function EstadisticasSection({
  datos,
  fase,
  error,
  refetch,
}: EstadisticasSectionProps): JSX.Element {
  if (fase === "cargando") {
    return <LoadingState />;
  }

  if (fase === "error" || !datos) {
    return <ErrorState message={error ?? "Error desconocido."} onRetry={refetch} />;
  }

  const regionales = datos.grafico_regionales ?? [];
  const dependencias = datos.grafico_dependencias ?? [];
  const alertas = datos.alertas_resultados ?? [];

  return (
    <div className="flex flex-col gap-6">
      {/* Ancho completo; el alto crece con la cantidad de unidades/direcciones. */}
      <div
        className="min-w-0"
        style={{ height: Math.max(CHART_HEIGHT, regionales.length * FILA_REGIONAL + 90) }}
      >
        <RegionalesBarChart data={regionales} />
      </div>

      <div className="min-w-0" style={{ height: CHART_HEIGHT }}>
        <ResultadosDonutChart data={alertas} />
      </div>

      <div className="min-w-0">
        <DependenciasBarChart data={dependencias} />
      </div>
    </div>
  );
}
