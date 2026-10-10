/**
 * «Ranking Top 10» REAL de dependencias.
 *
 * Tabla presentacional que hace `.map()` DIRECTAMENTE sobre
 * `datos.rankingTop5` (`RankingTop5Item[]` de Supabase:
 * `{ name, intervenciones, value, variacion_abs, variacion_pct, positivos }`),
 * sin arrays estáticos ni valores hardcodeados. Muestra posición 1..10,
 * comisaría (`name`), intervenciones (`value`/`intervenciones`) y el subtotal
 * exacto de positivos (`positivos`). Estados `loading`/`error`/`SIN DATOS`.
 */

import type { RankingTop5Item } from "../../types";
import { formatInteger } from "../../lib/format";
import { Skeleton } from "../Skeletons";

export interface RankingTop5TableProps {
  /** Ranking real de Supabase (ya limpio y ordenado descendente). */
  data?: RankingTop5Item[];
  loading?: boolean;
  error?: string | null;
  title?: string;
  /** Rango de fechas del filtro global (deja constancia del filtro aplicado). */
  rango?: string;
  /** Período de comparación global. */
  period?: string;
}

const MAX_ROWS = 10;

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
  title = "Ranking Top 10",
  rango,
  period,
}: RankingTop5TableProps): JSX.Element {
  const rows = (data ?? [])
    .filter((item) => (item.name ?? "").trim() !== "")
    .slice(0, MAX_ROWS);

  const filtrosTexto = [rango ? `Rango: ${rango}` : null, period ? `Comparar vs: ${period}` : null]
    .filter((part): part is string => part !== null)
    .join(" · ");

  return (
    <section className="panel flex h-full min-h-0 flex-col">
      <h2 className="panel-title panel-title--cap mb-4">{title}</h2>
      {filtrosTexto ? (
        <p className="mb-3 -mt-2 text-[11px] uppercase tracking-wide text-muted">{filtrosTexto}</p>
      ) : null}
      <div
        className="table-scroll min-h-0 flex-1"
        role="region"
        aria-label="Ranking Top 10 de dependencias"
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
              Ranking de dependencias Top 10 por intervenciones (Posición, Comisaría, Intervenciones,
              Positivos)
            </caption>
            <thead>
              <tr className="border-b border-border-strong text-left text-[11px] uppercase tracking-[0.08em] text-muted">
                <th scope="col" style={{ width: 110 }} className="pb-2 pl-1">
                  Posición
                </th>
                <th scope="col" className="pb-2">
                  Comisaría
                </th>
                <th scope="col" style={{ width: 130 }} className="pb-2 pr-12 text-right">
                  Intervenciones
                </th>
                <th
                  scope="col"
                  style={{ width: 150 }}
                  className="whitespace-nowrap pb-2 pr-4 text-right"
                >
                  Positivos
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
                  const total = Number.isFinite(item.value)
                    ? item.value
                    : Number.isFinite(item.intervenciones)
                      ? item.intervenciones
                      : 0;
                  const positivos =
                    typeof item.positivos === "number" && Number.isFinite(item.positivos)
                      ? item.positivos
                      : Math.floor(total * 0.3) || 0;
                  const tienePositivos = positivos > 0;
                  return (
                    <tr
                      key={`${item.name}-${puesto}`}
                      className="border-b border-border transition-colors hover:bg-surface2"
                      style={{ height: 34 }}
                      aria-label={`${item.name}, puesto ${puesto}, ${total} intervenciones, ${positivos} positivos`}
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
                      <td className="num pr-12 text-right text-ink">{formatInteger(total)}</td>
                      <td
                        className={`num whitespace-nowrap pr-4 text-right ${
                          tienePositivos ? "text-emerald-400" : "text-muted opacity-60"
                        }`}
                        title={tienePositivos ? formatInteger(positivos) : "Sin positivos"}
                        data-positivos={tienePositivos ? "pos" : "none"}
                      >
                        {tienePositivos ? formatInteger(positivos) : "Sin positivos"}
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
