/**
 * VIS-07 — "Ranking Top 5" de dependencias (RF-04.d–j).
 *
 * Tabla semántica de 4 columnas, hasta 5 filas (sin relleno), badge de posición,
 * destello de 600 ms al cambiar de puesto y estado vacío `SIN DATOS`. Navegable
 * por teclado (flechas arriba/abajo) con encabezados `scope="col"`.
 */

import { useEffect, useRef, useState } from "react";
import type { RankingItem } from "../types";
import { hasRealComparison } from "../lib/comparison";
import type { ComparisonPeriod } from "../lib/comparison";
import { formatInteger, formatVariation, toneColorVar } from "../lib/format";

export interface RankingTableProps {
  dependencias: RankingItem[];
  /** Período de comparación global (opcional; por defecto, datos del backend). */
  period?: ComparisonPeriod;
  /** Secuencia del snapshot para el cálculo determinista (opcional). */
  seq?: number;
}

function puestoChangeLabel(item: RankingItem): string {
  if (!item.puesto_previo || item.puesto_previo === item.puesto) return "";
  const delta = item.puesto_previo - item.puesto;
  if (delta > 0) return `subió ${delta} ${delta === 1 ? "puesto" : "puestos"}`;
  const down = Math.abs(delta);
  return `bajó ${down} ${down === 1 ? "puesto" : "puestos"}`;
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

export function RankingTable({ dependencias, period }: RankingTableProps): JSX.Element {
  const rowRefs = useRef<Array<HTMLTableRowElement | null>>([]);
  const previousPuestos = useRef<Map<string, number>>(new Map());
  const [flashing, setFlashing] = useState<Set<string>>(new Set());

  useEffect(() => {
    const changed = new Set<string>();
    const next = new Map<string, number>();
    for (const item of dependencias) {
      const previous = previousPuestos.current.get(item.dependencia_id);
      if (previous !== undefined && previous !== item.puesto) changed.add(item.dependencia_id);
      next.set(item.dependencia_id, item.puesto);
    }
    previousPuestos.current = next;
    if (changed.size === 0) return;
    setFlashing(changed);
    const id = window.setTimeout(() => setFlashing(new Set()), 600);
    return () => window.clearTimeout(id);
  }, [dependencias]);

  function focusRow(index: number): void {
    const target = rowRefs.current[index];
    target?.focus();
  }

  return (
    <section className="panel flex h-full min-h-0 flex-col">
      <h2 className="panel-title panel-title--cap mb-4">Ranking Top 5</h2>
      <div
        className="table-scroll min-h-0 flex-1"
        role="region"
        aria-label="Ranking Top 5 de dependencias"
        tabIndex={0}
      >
        <table className="w-full min-w-[520px] border-collapse text-sm">
          <caption className="sr-only">
            Ranking de dependencias Top 5 por intervenciones (Posición, Comisaría, Intervenciones,
            Variación)
          </caption>
          <thead>
            <tr className="border-b border-border-strong text-left text-[11px] uppercase tracking-[0.08em] text-muted">
              <th scope="col" style={{ width: 110 }} className="pb-2 pl-1">
                Posición
              </th>
              <th scope="col" className="pb-2">
                Comisaría
              </th>
              <th scope="col" style={{ width: 130 }} className="pb-2 pr-4 text-right">
                Intervenciones
              </th>
              <th scope="col" style={{ width: 210 }} className="pb-2 pr-1 text-right">
                Variación
              </th>
            </tr>
          </thead>
          <tbody>
            {dependencias.length === 0 ? (
              <tr>
                <td colSpan={4} className="py-10 text-center">
                  <span className="block font-display text-base font-semibold uppercase text-ink2">
                    SIN DATOS
                  </span>
                  <span className="text-xs text-muted">
                    sin datos en origen / sin datos en caché
                  </span>
                </td>
              </tr>
            ) : (
              dependencias.map((item, index) => {
                // Sólo la comparación real («ayer») del snapshot es mostrable.
                const hasReal = period === undefined || hasRealComparison(period);
                const variation = hasReal
                  ? formatVariation(item.variacion_abs, item.variacion_pct)
                  : null;
                const changeLabel = puestoChangeLabel(item);
                const style = posStyle(item.puesto);
                return (
                  <tr
                    key={item.dependencia_id || item.comisaria}
                    ref={(el) => {
                      rowRefs.current[index] = el;
                    }}
                    tabIndex={0}
                    onKeyDown={(event) => {
                      if (event.key === "ArrowDown") {
                        event.preventDefault();
                        focusRow(Math.min(index + 1, dependencias.length - 1));
                      } else if (event.key === "ArrowUp") {
                        event.preventDefault();
                        focusRow(Math.max(index - 1, 0));
                      }
                    }}
                    className={`border-b border-border transition-colors hover:bg-surface2 ${
                      flashing.has(item.dependencia_id) ? "row-flash" : ""
                    }`}
                    style={{ height: 34 }}
                    aria-label={`${item.comisaria}, puesto ${item.puesto}, ${item.intervenciones} intervenciones${
                      changeLabel ? `, ${changeLabel}` : ""
                    }`}
                  >
                    <td className="py-1 pl-1">
                      <span
                        className="flex h-6 w-6 items-center justify-center rounded-lg border text-xs font-semibold"
                        style={style}
                      >
                        {item.puesto}
                      </span>
                    </td>
                    <td className="pr-4 text-ink" title={item.comisaria}>
                      {item.comisaria}
                    </td>
                    <td className="num pr-4 text-right text-ink">
                      {formatInteger(item.intervenciones)}
                    </td>
                    <td className="pr-1 text-right">
                      {variation ? (
                        <span className="num" style={{ color: toneColorVar(variation.tone) }}>
                          <span aria-hidden="true">{variation.glyph} </span>
                          {variation.abs} {variation.pct}
                        </span>
                      ) : (
                        <span className="text-muted">—</span>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}
