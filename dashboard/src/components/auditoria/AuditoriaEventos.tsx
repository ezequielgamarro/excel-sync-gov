/**
 * Pestaña «Auditoría» (solo administradores): bitácora de todos los eventos del
 * sistema y qué hizo cada persona. Lee `auditoria_eventos` (solo `platform-admin`
 * puede leerla por RLS; la tabla es de solo anexado).
 */

import { useCallback, useEffect, useState } from "react";
import { ChevronLeft, ChevronRight, RefreshCw } from "lucide-react";
import { supabase } from "../../supabaseClient";
import {
  ACCIONES,
  ACCION_ETIQUETA,
  describirEvento,
  type EventoAuditoria,
} from "../../lib/auditoriaTexto";

const LIMITE = 50;

const FILTRO_CLASS =
  "touch-target rounded-[10px] border border-border bg-surface2 px-3 text-sm normal-case text-ink transition-colors focus-visible:border-accent";

const BOTON_CLASS =
  "touch-target inline-flex items-center justify-center gap-2 rounded-[10px] border border-border bg-surface2 px-3 text-xs font-semibold uppercase tracking-wide text-ink transition-colors hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:opacity-50";

interface Filtros {
  desde: string;
  hasta: string;
  accion: string;
  resultado: "" | "ok" | "error";
}

const FILTROS_VACIOS: Filtros = { desde: "", hasta: "", accion: "", resultado: "" };

function formatearFecha(iso: string): string {
  const fecha = new Date(iso);
  return Number.isNaN(fecha.getTime()) ? "—" : fecha.toLocaleString("es-AR");
}

export function AuditoriaEventos(): JSX.Element {
  const [filtros, setFiltros] = useState<Filtros>(FILTROS_VACIOS);
  const [usuarioTexto, setUsuarioTexto] = useState("");
  const [usuario, setUsuario] = useState("");
  const [page, setPage] = useState(0);
  const [eventos, setEventos] = useState<EventoAuditoria[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const id = window.setTimeout(() => {
      setPage(0);
      setUsuario(usuarioTexto.trim());
    }, 350);
    return () => window.clearTimeout(id);
  }, [usuarioTexto]);

  const cambiar = (cambio: Partial<Filtros>): void => {
    setPage(0);
    setFiltros((previos) => ({ ...previos, ...cambio }));
  };

  const cargar = useCallback(async (): Promise<void> => {
    setLoading(true);
    setError(null);
    try {
      let consulta = supabase.from("auditoria_eventos").select("*", { count: "exact" });
      if (filtros.desde) consulta = consulta.gte("created_at", `${filtros.desde}T00:00:00`);
      if (filtros.hasta) consulta = consulta.lte("created_at", `${filtros.hasta}T23:59:59.999`);
      if (filtros.accion) consulta = consulta.eq("accion", filtros.accion);
      if (filtros.resultado) consulta = consulta.eq("exito", filtros.resultado === "ok");
      if (usuario) {
        const literal = usuario.replace(/[\\%_]/g, (c) => "\\" + c);
        consulta = consulta.ilike("usuario_email", `%${literal}%`);
      }
      const { data, count, error: queryError } = await consulta
        .order("created_at", { ascending: false })
        .order("id", { ascending: false })
        .range(page * LIMITE, (page + 1) * LIMITE - 1);
      if (queryError) {
        setError(queryError.message);
        setEventos([]);
        setTotal(0);
        return;
      }
      setEventos((data ?? []) as EventoAuditoria[]);
      setTotal(typeof count === "number" ? count : 0);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo cargar la auditoría.");
    } finally {
      setLoading(false);
    }
  }, [filtros, usuario, page]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  const paginas = Math.max(1, Math.ceil(total / LIMITE));
  const hayFiltros = Object.values(filtros).some((v) => v !== "") || usuarioTexto !== "";

  return (
    <div className="flex flex-col gap-6" data-testid="auditoria-eventos">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-xl font-semibold uppercase tracking-wide text-ink">
            Auditoría
          </h2>
          <p className="text-sm text-muted">
            Registro de todos los movimientos del sistema: qué hizo cada persona y cuándo.
          </p>
        </div>
        <button type="button" onClick={() => void cargar()} disabled={loading} className={BOTON_CLASS}>
          <RefreshCw size={14} aria-hidden="true" />
          Actualizar
        </button>
      </div>

      <div
        role="search"
        aria-label="Filtros de la auditoría"
        className="panel flex flex-wrap items-end gap-3"
      >
        <label className="flex flex-col gap-1 text-[11px] uppercase tracking-wide text-muted">
          Desde
          <input
            type="date"
            className={FILTRO_CLASS}
            value={filtros.desde}
            max={filtros.hasta || undefined}
            onChange={(e) => cambiar({ desde: e.target.value })}
          />
        </label>
        <label className="flex flex-col gap-1 text-[11px] uppercase tracking-wide text-muted">
          Hasta
          <input
            type="date"
            className={FILTRO_CLASS}
            value={filtros.hasta}
            min={filtros.desde || undefined}
            onChange={(e) => cambiar({ hasta: e.target.value })}
          />
        </label>
        <label className="flex min-w-[220px] flex-1 flex-col gap-1 text-[11px] uppercase tracking-wide text-muted">
          Empleado (email)
          <input
            type="search"
            className={FILTRO_CLASS}
            placeholder="Buscar por usuario…"
            value={usuarioTexto}
            onChange={(e) => setUsuarioTexto(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1 text-[11px] uppercase tracking-wide text-muted">
          Acción
          <select
            className={FILTRO_CLASS}
            value={filtros.accion}
            onChange={(e) => cambiar({ accion: e.target.value })}
          >
            <option value="">Todas</option>
            {ACCIONES.map((a) => (
              <option key={a} value={a}>
                {ACCION_ETIQUETA[a]}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-[11px] uppercase tracking-wide text-muted">
          Resultado
          <select
            className={FILTRO_CLASS}
            value={filtros.resultado}
            onChange={(e) => cambiar({ resultado: e.target.value as Filtros["resultado"] })}
          >
            <option value="">Todos</option>
            <option value="ok">Correcto</option>
            <option value="error">Con error</option>
          </select>
        </label>
        {hayFiltros ? (
          <button
            type="button"
            className={BOTON_CLASS}
            onClick={() => {
              setUsuarioTexto("");
              setUsuario("");
              cambiar(FILTROS_VACIOS);
            }}
          >
            Limpiar filtros
          </button>
        ) : null}
      </div>

      {error ? (
        <p
          role="alert"
          className="rounded-[12px] border border-neg/50 bg-neg/10 px-4 py-3 text-sm font-semibold text-neg"
        >
          {error}
        </p>
      ) : null}

      <div className="panel overflow-x-auto p-0">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-border text-left text-[11px] uppercase tracking-wide text-muted">
              <th className="px-4 py-3 font-medium">Fecha y hora</th>
              <th className="px-4 py-3 font-medium">Empleado</th>
              <th className="px-4 py-3 font-medium">Rol</th>
              <th className="px-4 py-3 font-medium">Acción</th>
              <th className="px-4 py-3 font-medium">Qué hizo</th>
              <th className="px-4 py-3 font-medium">Resultado</th>
            </tr>
          </thead>
          <tbody>
            {loading && eventos.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-muted">
                  Cargando eventos…
                </td>
              </tr>
            ) : null}
            {!loading && eventos.length === 0 && !error ? (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-muted" role="status">
                  SIN EVENTOS
                </td>
              </tr>
            ) : null}
            {eventos.map((evento) => (
              <tr key={evento.id} className="border-b border-border/60 align-top last:border-b-0">
                <td className="num whitespace-nowrap px-4 py-3 text-ink2">
                  {formatearFecha(evento.created_at)}
                </td>
                <td className="px-4 py-3 text-ink2">{evento.usuario_email}</td>
                <td className="px-4 py-3 capitalize text-muted">{evento.rol || "—"}</td>
                <td className="whitespace-nowrap px-4 py-3 font-semibold text-ink">
                  {ACCION_ETIQUETA[evento.accion] ?? evento.accion}
                </td>
                <td className="min-w-[280px] px-4 py-3 text-ink2">{describirEvento(evento)}</td>
                <td className="px-4 py-3">
                  <span
                    className={
                      evento.exito
                        ? "text-xs font-semibold uppercase text-emerald-400"
                        : "text-xs font-semibold uppercase text-neg"
                    }
                  >
                    {evento.exito ? "Correcto" : "Error"}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <nav aria-label="Paginación" className="flex items-center justify-between gap-3 text-sm text-muted">
        <span>
          {total} evento{total === 1 ? "" : "s"} · Página {page + 1} de {paginas}
        </span>
        <div className="flex gap-2">
          <button
            type="button"
            aria-label="Página anterior"
            disabled={page === 0 || loading}
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            className={BOTON_CLASS}
          >
            <ChevronLeft size={16} aria-hidden="true" />
          </button>
          <button
            type="button"
            aria-label="Página siguiente"
            disabled={page + 1 >= paginas || loading}
            onClick={() => setPage((p) => p + 1)}
            className={BOTON_CLASS}
          >
            <ChevronRight size={16} aria-hidden="true" />
          </button>
        </div>
      </nav>
    </div>
  );
}
