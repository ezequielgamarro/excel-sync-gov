/**
 * Dona de `alertas_resultados` (hoja `DASHBOARD_WEB`).
 *
 * Excluye las entradas con nombre en blanco y la fila agregada
 * «... POSITIVO-NEGATIVO» cuando su valor es 0. La leyenda muestra nombre +
 * valor, con el mismo lenguaje visual que `DistributionDonutChart`.
 */

import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from "recharts";
import type { EstadisticaItem } from "../../types";
import { formatInteger } from "../../lib/format";
import { CHART_PALETTE } from "../charts/filters";

export interface ResultadosDonutChartProps {
  data: EstadisticaItem[];
  title?: string;
}

const RE_NEGATIVO = /NE[GV]ATIVO/i;
const RE_POSITIVO = /POSITIVO/i;

function esAgregadoPositivoNegativo(name: string): boolean {
  return RE_POSITIVO.test(name) && RE_NEGATIVO.test(name);
}

interface Slice {
  name: string;
  value: number;
  color: string;
}

interface TooltipProps {
  active?: boolean;
  payload?: Array<{ payload: Slice }>;
}

function DarkTooltip({ active, payload }: TooltipProps): JSX.Element | null {
  if (!active || !payload || payload.length === 0) return null;
  const slice = payload[0].payload;
  return (
    <div
      className="rounded-[10px] border border-border-strong p-3 text-sm"
      style={{
        backgroundColor: "var(--bg-surface-2)",
        color: "var(--text-primary)",
        boxShadow: "0 12px 32px -18px rgba(0,0,0,0.95)",
      }}
    >
      <p className="font-display text-base font-semibold uppercase tracking-wide">{slice.name}</p>
      <p className="num mt-1">{formatInteger(slice.value)}</p>
    </div>
  );
}

export function ResultadosDonutChart({
  data,
  title = "Resultados de Alertas",
}: ResultadosDonutChartProps): JSX.Element {
  const slices: Slice[] = data
    .filter((item) => item.name.trim() !== "")
    .filter((item) => !(esAgregadoPositivoNegativo(item.name) && item.value === 0))
    .slice()
    .sort((a, b) => b.value - a.value)
    .map((item, index) => ({
      name: item.name,
      value: item.value,
      color: CHART_PALETTE[index % CHART_PALETTE.length],
    }));

  return (
    <section className="panel flex h-full min-h-0 flex-col overflow-hidden">
      <h2 className="panel-title panel-title--cap mb-2">{title}</h2>
      <div
        className="flex min-h-0 min-w-0 flex-1 flex-col items-center gap-3 lg:flex-row lg:items-stretch lg:gap-4"
        data-testid="chart-estadisticas-resultados"
      >
        {slices.length === 0 ? (
          <p className="flex h-full items-center justify-center text-sm text-muted" role="status">
            SIN DATOS
          </p>
        ) : (
          <>
            <div className="relative min-h-[150px] w-full min-w-0 flex-1 overflow-hidden lg:min-h-0">
              <div className="absolute inset-0">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={slices}
                      dataKey="value"
                      nameKey="name"
                      cx="50%"
                      cy="50%"
                      innerRadius="55%"
                      outerRadius="82%"
                      paddingAngle={2}
                      stroke="none"
                      isAnimationActive={false}
                    >
                      {slices.map((slice) => (
                        <Cell key={slice.name} fill={slice.color} />
                      ))}
                    </Pie>
                    <Tooltip content={<DarkTooltip />} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </div>

            <ul
              aria-label="Leyenda de resultados"
              className="flex w-full min-w-0 shrink-0 flex-col justify-center gap-1.5 pr-1 text-xs lg:w-72 lg:gap-2"
            >
              {slices.map((slice) => (
                <li key={slice.name} className="flex items-center gap-2">
                  <span
                    aria-hidden="true"
                    className="inline-block h-3 w-3 shrink-0 rounded-sm"
                    style={{ backgroundColor: slice.color }}
                  />
                  <span className="min-w-0 flex-1 break-words text-ink2">{slice.name}</span>
                  <span className="num shrink-0 pl-3 text-muted">{formatInteger(slice.value)}</span>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </section>
  );
}
