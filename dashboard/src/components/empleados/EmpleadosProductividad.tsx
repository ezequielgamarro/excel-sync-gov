/**
 * Pestaña «Empleados» (solo administradores): KPIs y gráficos que comparan la
 * productividad de cada empleado (registros cargados, errores y correcciones),
 * calculados a partir de la auditoría (`resumen_empleados`).
 */

import { useCallback, useEffect, useMemo, useState } from "react";
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
import { supabase } from "../../supabaseClient";
import { formatInteger } from "../../lib/format";
import {
  aEmpleados,
  maximoPor,
  ordenarPor,
  type Empleado,
  type ResumenEmpleadoFila,
} from "../../lib/empleados";

const FILTRO_CLASS =
  "touch-target rounded-[10px] border border-border bg-surface2 px-3 text-sm normal-case text-ink transition-colors focus-visible:border-accent";

interface KpiProps {
  label: string;
  value: string;
  detalle: string;
  testKey: string;
}

function Kpi({ label, value, detalle, testKey }: KpiProps): JSX.Element {
  return (
    <article
      className="kpi-card relative flex min-h-[128px] flex-col justify-between gap-3 overflow-hidden p-4"
      role="group"
      aria-label={`${label}: ${value}`}
      data-kpi={testKey}
    >
      <span
        aria-hidden="true"
        className="absolute inset-y-0 left-0 w-[3px]"
        style={{ backgroundColor: "var(--accent)" }}
      />
      <span className="label-eyebrow text-muted">{label}</span>
      <span className="kpi-value num text-[36px] font-semibold leading-[1.02] text-ink">
        {value}
      </span>
      <span className="truncate text-xs text-muted" title={detalle}>
        {detalle}
      </span>
    </article>
  );
}

function DarkTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ name: string; value: number; color?: string }>;
  label?: string;
}): JSX.Element | null {
  if (!active || !payload || payload.length === 0) return null;
  return (
    <div
      className="rounded-[10px] border border-border-strong p-3 text-sm"
      style={{
        backgroundColor: "var(--bg-surface-2)",
        color: "var(--text-primary)",
        boxShadow: "0 12px 32px -18px rgba(0,0,0,0.95)",
      }}
    >
      <p className="font-display text-base font-semibold uppercase tracking-wide">{label}</p>
      {payload.map((p) => (
        <p key={p.name} className="num text-xs" style={{ color: p.color }}>
          {p.name}: {formatInteger(p.value)}
        </p>
      ))}
    </div>
  );
}

const EJE = { fill: "var(--text-muted)", fontSize: 12 };

interface GraficoProps {
  titulo: string;
  empleados: Empleado[];
  series: Array<{ clave: keyof Empleado; nombre: string; color: string; apilada?: boolean }>;
  testId: string;
}

/** Barras horizontales por empleado; altura según la cantidad de filas. */
function GraficoEmpleados({ titulo, empleados, series, testId }: GraficoProps): JSX.Element {
  const alto = Math.max(300, empleados.length * 52 + 90);
  return (
    <section className="panel flex min-h-0 flex-col overflow-hidden">
      <h2 className="panel-title panel-title--cap mb-2">{titulo}</h2>
      <div className="relative min-w-0" style={{ height: alto }} data-testid={testId}>
        {empleados.length === 0 ? (
          <p className="flex h-full items-center justify-center text-sm text-muted" role="status">
            SIN DATOS
          </p>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              layout="vertical"
              data={empleados}
              margin={{ top: 8, right: 56, bottom: 8, left: 8 }}
              accessibilityLayer
            >
              <CartesianGrid horizontal={false} vertical stroke="var(--border)" strokeDasharray="2 6" />
              <XAxis
                type="number"
                allowDecimals={false}
                stroke="var(--border-strong)"
                tick={EJE}
                tickLine={false}
              />
              <YAxis
                type="category"
                dataKey="nombre"
                width={150}
                interval={0}
                stroke="var(--border-strong)"
                tick={{ fill: "var(--text-secondary)", fontSize: 13 }}
                tickLine={false}
              />
              <Tooltip content={<DarkTooltip />} cursor={{ fill: "var(--accent-soft)" }} />
              <Legend verticalAlign="top" height={36} />
              {series.map((s, i) => (
                <Bar
                  key={String(s.clave)}
                  dataKey={s.clave as string}
                  name={s.nombre}
                  fill={s.color}
                  stackId={s.apilada ? "a" : undefined}
                  maxBarSize={s.apilada ? 28 : 18}
                  radius={[0, 6, 6, 0]}
                  isAnimationActive
                  animationDuration={1000}
                  animationEasing="ease-out"
                >
                  {i === series.length - 1 || !s.apilada ? (
                    <LabelList
                      dataKey={s.clave as string}
                      position={s.apilada ? "insideRight" : "right"}
                      formatter={(v: number) => (v > 0 ? formatInteger(v) : "")}
                      style={{ fill: "var(--text-primary)", fontSize: 12 }}
                    />
                  ) : null}
                </Bar>
              ))}
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </section>
  );
}

function formatearFecha(iso: string | null): string {
  if (!iso) return "—";
  const fecha = new Date(iso);
  return Number.isNaN(fecha.getTime()) ? "—" : fecha.toLocaleString("es-AR");
}

export function EmpleadosProductividad(): JSX.Element {
  const [desde, setDesde] = useState("");
  const [hasta, setHasta] = useState("");
  const [filas, setFilas] = useState<ResumenEmpleadoFila[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(async (): Promise<void> => {
    setLoading(true);
    setError(null);
    try {
      const { data, error: rpcError } = await supabase.rpc("resumen_empleados", {
        p_desde: desde || null,
        p_hasta: hasta || null,
      });
      if (rpcError) {
        setError(rpcError.message);
        setFilas([]);
        return;
      }
      setFilas((data ?? []) as ResumenEmpleadoFila[]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo cargar la productividad.");
    } finally {
      setLoading(false);
    }
  }, [desde, hasta]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  const empleados = useMemo(() => aEmpleados(filas), [filas]);
  const porCargados = useMemo(() => ordenarPor(empleados, "cargados"), [empleados]);
  const porErrores = useMemo(() => ordenarPor(empleados, "errores"), [empleados]);
  const masCargados = maximoPor(empleados, "cargados");
  const masErrores = maximoPor(empleados, "errores");
  const totalCargados = empleados.reduce((acc, e) => acc + e.cargados, 0);
  const totalErrores = empleados.reduce((acc, e) => acc + e.errores, 0);
  const tasaGlobal =
    totalCargados + totalErrores > 0 ? (totalErrores / (totalCargados + totalErrores)) * 100 : 0;

  return (
    <div className="flex flex-col gap-6" data-testid="empleados-productividad">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="font-display text-xl font-semibold uppercase tracking-wide text-ink">
            Empleados
          </h2>
          <p className="text-sm text-muted">
            Productividad y errores de cada empleado, según los movimientos auditados.
          </p>
        </div>
        <div role="search" aria-label="Período" className="flex flex-wrap items-end gap-3">
          <label className="flex flex-col gap-1 text-[11px] uppercase tracking-wide text-muted">
            Desde
            <input
              type="date"
              className={FILTRO_CLASS}
              value={desde}
              max={hasta || undefined}
              onChange={(e) => setDesde(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-[11px] uppercase tracking-wide text-muted">
            Hasta
            <input
              type="date"
              className={FILTRO_CLASS}
              value={hasta}
              min={desde || undefined}
              onChange={(e) => setHasta(e.target.value)}
            />
          </label>
          {desde || hasta ? (
            <button
              type="button"
              className="touch-target rounded-[10px] border border-border bg-surface2 px-4 text-xs font-semibold uppercase tracking-wide text-ink transition-colors hover:border-accent hover:text-accent"
              onClick={() => {
                setDesde("");
                setHasta("");
              }}
            >
              Limpiar
            </button>
          ) : null}
        </div>
      </div>

      {error ? (
        <p
          role="alert"
          className="rounded-[12px] border border-neg/50 bg-neg/10 px-4 py-3 text-sm font-semibold text-neg"
        >
          {error}
        </p>
      ) : null}

      <div className="grid grid-cols-1 gap-[var(--grid-gutter)] sm:grid-cols-2 xl:grid-cols-4">
        <Kpi
          label="MÁS REGISTROS CARGADOS"
          value={formatInteger(masCargados?.cargados ?? 0)}
          detalle={masCargados?.email ?? "Sin datos"}
          testKey="mas-cargados"
        />
        <Kpi
          label="MÁS ERRORES"
          value={formatInteger(masErrores?.errores ?? 0)}
          detalle={masErrores?.email ?? "Sin errores registrados"}
          testKey="mas-errores"
        />
        <Kpi
          label="TOTAL REGISTROS CARGADOS"
          value={formatInteger(totalCargados)}
          detalle={`${empleados.length} empleado${empleados.length === 1 ? "" : "s"} con actividad`}
          testKey="total-cargados"
        />
        <Kpi
          label="TASA DE ERROR GLOBAL"
          value={`${tasaGlobal.toLocaleString("es-AR", { maximumFractionDigits: 1 })}%`}
          detalle={`${formatInteger(totalErrores)} intento${totalErrores === 1 ? "" : "s"} fallido${
            totalErrores === 1 ? "" : "s"
          }`}
          testKey="tasa-error"
        />
      </div>

      <GraficoEmpleados
        titulo="Registros cargados por empleado"
        empleados={porCargados}
        series={[{ clave: "cargados", nombre: "Registros cargados", color: "#3b82f6" }]}
        testId="chart-empleados-cargados"
      />

      <GraficoEmpleados
        titulo="Errores y correcciones por empleado"
        empleados={porErrores}
        series={[
          { clave: "errores", nombre: "Errores (intentos fallidos)", color: "#ef4444" },
          { clave: "ediciones", nombre: "Ediciones", color: "#f59e0b" },
          { clave: "eliminaciones", nombre: "Eliminaciones", color: "#8b5cf6" },
        ]}
        testId="chart-empleados-errores"
      />

      <GraficoEmpleados
        titulo="Comparativa de productividad"
        empleados={porCargados}
        series={[
          { clave: "cargados", nombre: "Cargados", color: "#22c55e", apilada: true },
          { clave: "importaciones", nombre: "Importaciones", color: "#3b82f6", apilada: true },
        ]}
        testId="chart-empleados-comparativa"
      />

      <div className="panel overflow-x-auto p-0">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-border text-left text-[11px] uppercase tracking-wide text-muted">
              <th className="px-4 py-3 font-medium">Empleado</th>
              <th className="px-4 py-3 text-right font-medium">Cargados</th>
              <th className="px-4 py-3 text-right font-medium">Ediciones</th>
              <th className="px-4 py-3 text-right font-medium">Eliminaciones</th>
              <th className="px-4 py-3 text-right font-medium">Importaciones</th>
              <th className="px-4 py-3 text-right font-medium">Errores</th>
              <th className="px-4 py-3 text-right font-medium">Tasa de error</th>
              <th className="px-4 py-3 font-medium">Último movimiento</th>
            </tr>
          </thead>
          <tbody>
            {loading && empleados.length === 0 ? (
              <tr>
                <td colSpan={8} className="px-4 py-6 text-center text-muted">
                  Cargando empleados…
                </td>
              </tr>
            ) : null}
            {!loading && empleados.length === 0 && !error ? (
              <tr>
                <td colSpan={8} className="px-4 py-6 text-center text-muted" role="status">
                  SIN DATOS
                </td>
              </tr>
            ) : null}
            {porCargados.map((e) => (
              <tr key={e.email} className="border-b border-border/60 last:border-b-0">
                <td className="px-4 py-3 text-ink2">{e.email}</td>
                <td className="num px-4 py-3 text-right text-ink">{formatInteger(e.cargados)}</td>
                <td className="num px-4 py-3 text-right text-ink2">{formatInteger(e.ediciones)}</td>
                <td className="num px-4 py-3 text-right text-ink2">
                  {formatInteger(e.eliminaciones)}
                </td>
                <td className="num px-4 py-3 text-right text-ink2">
                  {formatInteger(e.importaciones)}
                </td>
                <td className="num px-4 py-3 text-right text-ink2">{formatInteger(e.errores)}</td>
                <td className="num px-4 py-3 text-right text-ink2">
                  {e.tasaError.toLocaleString("es-AR", { maximumFractionDigits: 1 })}%
                </td>
                <td className="num whitespace-nowrap px-4 py-3 text-ink2">
                  {formatearFecha(e.ultimoEvento)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-muted">
        Errores = intentos fallidos al guardar, importar o exportar. Tasa de error = errores /
        (cargados + errores). Las cargas hechas por el Apps Script no se atribuyen a ningún empleado.
      </p>
    </div>
  );
}
