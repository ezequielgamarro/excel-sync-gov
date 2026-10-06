/**
 * «Ranking Top 5» REAL de dependencias.
 *
 * Tabla presentacional que hace `.map()` DIRECTAMENTE sobre
 * `datos.rankingTop5` (`RankingTop5Item[]` del backend:
 * `{ name, intervenciones, value, variacion_abs, variacion_pct }`), sin arrays
 * estáticos ni valores hardcodeados (p. ej. el viejo 8.420 del snapshot
 * semilla). Muestra posición 1..5, comisaría (`name`), intervenciones
 * (`value`/`intervenciones`) y variación (`variacion_abs`/`variacion_pct`; «—»
 * si no hay base anterior). Estados `loading`/`error`/`SIN DATOS`.
 */

import type { RankingTop5Item } from "../../types";
import { formatInteger, formatVariation } from "../../lib/format";
import type { VariationTone } from "../../lib/format";
import { Skeleton } from "../Skeletons";

export interface RankingTop5TableProps {
  /** Ranking real del backend (ya limpio y ordenado descendente). */
  data?: RankingTop5Item[];
  loading?: boolean;
  error?: string | null;
  title?: string;
}

const MAX_ROWS = 5;

interface VariacionDisplay {
  /** Texto completo con glifo y signo (nunca depende sólo del color). */
  text: string;
  tone: VariationTone;
}

/**
 * Variación legible: `▲ +abs (+pct)` si sube, `▼ −abs (−pct)` si baja y `—`
 * cuando no hay base (`variacion_pct === null`) o la variación es cero.
 */
function getVariacion(item: RankingTop5Item): VariacionDisplay {
  if (item.variacion_pct === null || item.variacion_abs === 0) {
    return { text: "—", tone: "flat" };
  }
  const parts = formatVariation(item.variacion_abs, item.variacion_pct);
  if (!parts) return { text: "—", tone: "flat" };
  return { text: parts.text, tone: parts.tone };
}

/** Cyan táctico para subidas, rojo tenue para bajadas, gris neutro en «—». */
function variacionStyle(tone: VariationTone): { color: string; opacity: number } {
  if (tone === "pos") return { color: "var(--accent-bright)", opacity: 1 };
  if (tone === "neg") return { color: "var(--neg)", opacity: 0.75 };
  return { color: "var(--text-secondary)", opacity: 1 };
}

function posStyle(puesto: number): { backgroundColor: string; color: string; border: string } {
  if (puesto === 1) {
    return { backgroundColor: "var(--accent)", color: "#04070F", border: "var(--accent)" };
  }
  if (puesto <= 3) {
    return {
      backgroundColor: "var(--accent-soft)",
      color: "var(--accent-bright)",
      border: "var(--border-strong)",
    };
  }
  return {
    backgroundColor: "var(--bg-surface-3)",
    color: "var(--text-secondary)",
    border: "var(--border)",
  };
}

export function RankingTop5Table({
  data,
  loading = false,
  error = null,
  title = "Ranking Top 5",
}: RankingTop5TableProps): JSX.Element {
  const rows = (data ?? [])
    .filter((item) => item.name.trim() !== "")
    .slice(0, MAX_ROWS);

  return (
    <section className="panel flex h-full min-h-0 flex-col">
      <h2 className="panel-title panel-title--cap mb-4">{title}</h2>
      <div
        className="table-scroll min-h-0 flex-1"
        role="region"
        aria-label="Ranking Top 5 de dependencias"
        data-testid="ranking-top5"
      >
        {loading && rows.length === 0 ? (
          <div className="flex flex-col gap-3" role="status" aria-label="Cargando ranking…">
            {Array.from({ length: MAX_ROWS }).map((_, index) => (
              <Skeleton key={index} className="h-8 w-full" />
            ))}
          </div>
        ) : (
          <table className="w-full min-w-[520px] border-collapse text-sm">
            <caption className="sr-only">
              Ranking de dependencias Top 5 por intervenciones (Posición, Comisaría,
              Intervenciones, Variación)
            </caption>
            <thead>
              <tr className="border-b border-border-strong text-left text-[11px] uppercase tracking-[0.08em] text-muted">
                <th scope="col" style={{ width: 110 }} className="pb-2 pl-1">
                  Posición
                </th>
                <th scope="col" className="pb-2">
                  Comisaría
                </th>
                <th scope="col" style={{ width: 130 }} className="pb-2 pr-8 text-right">
                  Intervenciones
                </th>
                <th scope="col" style={{ width: 130 }} className="pb-2 pr-4 text-right">
                  Variación
                </th>
              </tr>
            </thead>
            <tbody>
              {error && rows.length === 0 ? (
                <tr>
                  <td colSpan={4} className="py-10 text-center text-neg" role="alert">
                    No se pudo cargar el ranking. {error}
                  </td>
                </tr>
              ) : rows.length === 0 ? (
                <tr>
                  <td colSpan={4} className="py-10 text-center">
                    <span className="block font-display text-base font-semibold uppercase text-ink2">
                      SIN DATOS
                    </span>
                    <span className="text-xs text-muted">sin datos en origen</span>
                  </td>
                </tr>
              ) : (
                rows.map((item, index) => {
                  const puesto = index + 1;
                  const variacion = getVariacion(item);
                  return (
                    <tr
                      key={`${item.name}-${puesto}`}
                      className="border-b border-border transition-colors hover:bg-surface2"
                      style={{ height: 34 }}
                      aria-label={`${item.name}, puesto ${puesto}, ${item.intervenciones} intervenciones`}
                    >
                      <td className="py-1 pl-1">
                        <span
                          className="flex h-6 w-6 items-center justify-center rounded-lg border text-xs font-semibold"
                          style={posStyle(puesto)}
                        >
                          {puesto}
                        </span>
                      </td>
                      <td className="pr-4 text-ink" title={item.name}>
                        {item.name}
                      </td>
                      <td className="num pr-8 text-right text-ink">
                        {formatInteger(item.value)}
                      </td>
                      <td
                        className="num pr-4 text-right"
                        style={variacionStyle(variacion.tone)}
                        title={variacion.text}
                        aria-label={`Variación: ${variacion.text}`}
                        data-variation={variacion.tone}
                      >
                        {variacion.text}
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}
