/**
 * Los 6 KPIs del Resumen General expresados en gráficos:
 * - Resultado de las consultas (positivos vs negativos).
 * - Consultas por tipo (personas, vehículos, armas, elementos).
 * - Los 6 KPIs: período actual vs período anterior.
 */

import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type { EstadisticaItem, EstadisticasTotales } from "../../types";
import { formatInteger } from "../../lib/format";
import { BarrasHorizontalesChart } from "../charts/BarrasHorizontalesChart";
import { DistributionDonutChart } from "../charts/DistributionDonutChart";

const COLOR_ACTUAL = "#4cc2ff";
const COLOR_ANTERIOR = "#64748b";

const KPIS: ReadonlyArray<{ key: keyof EstadisticasTotales; nombre: string }> = [
  { key: "total_intervenciones", nombre: "Intervenciones" },
  { key: "total_positivos", nombre: "Positivos" },
  { key: "consultas_personas", nombre: "Personas" },
  { key: "consultas_vehiculos", nombre: "Vehículos" },
  { key: "consultas_armas", nombre: "Armas" },
  { key: "consultas_elementos", nombre: "Elementos" },
];

export interface KpiResumenChartsProps {
  totales?: EstadisticasTotales;
  totalesPrevios?: EstadisticasTotales;
  loading?: boolean;
  error?: string | null;
}

export function KpiResumenCharts({
  totales,
  totalesPrevios,
  loading = false,
  error = null,
}: KpiResumenChartsProps): JSX.Element {
  const valor = (t: EstadisticasTotales | undefined, key: keyof EstadisticasTotales): number =>
    t?.[key] ?? 0;

  const total = valor(totales, "total_intervenciones");
  const positivos = valor(totales, "total_positivos");
  const resultados = [
    { key: "positivos", label: "Positivos", value: positivos },
    { key: "negativos", label: "Negativos", value: Math.max(total - positivos, 0) },
  ];

  const porTipo: EstadisticaItem[] = [
    { name: "Personas", value: valor(totales, "consultas_personas") },
    { name: "Vehículos", value: valor(totales, "consultas_vehiculos") },
    { name: "Armas", value: valor(totales, "consultas_armas") },
    { name: "Elementos", value: valor(totales, "consultas_elementos") },
  ];

  const comparacion = KPIS.map(({ key, nombre }) => ({
    nombre,
    actual: valor(totales, key),
    anterior: valor(totalesPrevios, key),
  }));

  return (
    <div className="flex flex-col gap-[var(--grid-gutter)]">
      <div className="grid grid-cols-[repeat(auto-fit,minmax(min(100%,360px),1fr))] gap-[var(--grid-gutter)]">
        <div className="grid min-w-0" style={{ minHeight: 240 }}>
          <DistributionDonutChart
            title="Resultado de las Consultas"
            groups={resultados}
            loading={loading}
            error={error}
          />
        </div>
        <div className="grid min-w-0">
          <BarrasHorizontalesChart
            title="Consultas por Tipo"
            testId="chart-kpi-tipos"
            data={porTipo}
            loading={loading}
            error={error}
          />
        </div>
      </div>

      <section className="panel flex min-w-0 flex-col">
        <h2 className="panel-title panel-title--cap mb-1">KPIs: Período Actual vs Anterior</h2>
        <p className="mb-2 text-xs text-muted">
          Los seis indicadores del Resumen General, comparados con el período inmediato anterior.
        </p>
        <div style={{ height: 300 }} data-testid="chart-kpi-comparacion">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={comparacion} margin={{ top: 20, right: 8, bottom: 8, left: 0 }}>
              <CartesianGrid stroke="var(--border)" strokeDasharray="2 6" vertical={false} />
              <XAxis
                dataKey="nombre"
                stroke="var(--border-strong)"
                tick={{ fill: "var(--text-secondary)", fontSize: 12 }}
                tickLine={false}
              />
              <YAxis
                stroke="var(--border-strong)"
                tick={{ fill: "var(--text-muted)", fontSize: 12 }}
                tickLine={false}
                width={48}
                allowDecimals={false}
              />
              <Tooltip
                cursor={{ fill: "var(--accent-soft)" }}
                formatter={(v: number) => formatInteger(v)}
                contentStyle={{
                  backgroundColor: "var(--bg-surface-2)",
                  border: "1px solid var(--border-strong)",
                  borderRadius: 10,
                  color: "var(--text-primary)",
                }}
              />
              <Legend verticalAlign="top" height={28} />
              <Bar dataKey="actual" name="Período actual" fill={COLOR_ACTUAL} radius={[3, 3, 0, 0]}>
                <LabelList
                  dataKey="actual"
                  position="top"
                  fill="var(--text-primary)"
                  fontSize={11}
                  formatter={(v: number) => formatInteger(v)}
                />
              </Bar>
              <Bar
                dataKey="anterior"
                name="Período anterior"
                fill={COLOR_ANTERIOR}
                radius={[3, 3, 0, 0]}
              >
                <LabelList
                  dataKey="anterior"
                  position="top"
                  fill="var(--text-muted)"
                  fontSize={11}
                  formatter={(v: number) => formatInteger(v)}
                />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </section>
    </div>
  );
}
