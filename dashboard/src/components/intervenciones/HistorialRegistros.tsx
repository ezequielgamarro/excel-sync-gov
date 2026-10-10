/**
 * Módulo «Historial»: gestión de los registros cargados.
 *
 * Carga nativa de Supabase (tabla `intervenciones_diarias`, paginada) al montar
 * y permite editar (modal con `FormularioIntervencion` + `PUT`) y eliminar
 * (`DELETE`) cada fila, recargando la página actual tras cada operación. Todas
 * las operaciones toleran errores sin romper la vista.
 */

import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { ChevronLeft, ChevronRight, Pencil, Trash2, X } from "lucide-react";
import {
  actualizarIntervencion,
  eliminarIntervencion,
  type Intervencion,
  type IntervencionCreate,
} from "../../data/api";
import { supabase } from "../../supabaseClient";
import {
  FormularioIntervencion,
  SISTEMAS_UTILIZADOS,
  type FormValuesIntervencion,
} from "./FormularioIntervencion";
import { DIRECCIONES, UNIDADES_REGIONALES } from "../../data/dependencias";
import { INTERVENCIONES_REFRESH_EVENT } from "../../data/importarIntervenciones";
import { mensajeDeError, registrarEvento } from "../../lib/auditoria";

/** Convierte una fila persistida a valores de formulario (fecha vacía = `""`). */
function aValores(registro: Intervencion): FormValuesIntervencion {
  return {
    fecha_consulta: registro.fecha_consulta ?? "",
    hora_consulta: registro.hora_consulta,
    jerarquia: registro.jerarquia,
    personal_policial: registro.personal_policial,
    jefatura_regional: registro.jefatura_regional,
    dependencia: registro.dependencia,
    tipo_consulta: registro.tipo_consulta,
    identificacion: registro.identificacion,
    detalle_tipo: registro.detalle_tipo,
    resultado_consulta: registro.resultado_consulta,
    causas: registro.causas,
    numero_registro: registro.numero_registro,
    autoridad_judicial: registro.autoridad_judicial,
    sistema_utilizado: registro.sistema_utilizado,
    tramite_devuelto: registro.tramite_devuelto,
    hora_respuesta: registro.hora_respuesta,
    personal_informa: registro.personal_informa,
    cargo_informa: registro.cargo_informa,
    operativo_preventivo: registro.operativo_preventivo,
    allanamiento: registro.allanamiento,
    mini_resena: registro.mini_resena,
    legajo: registro.legajo ?? "",
    lugar_hecho: registro.lugar_hecho ?? "",
    detalle_identificacion: registro.detalle_identificacion ?? "",
  };
}

const ACTION_BUTTON_CLASS =
  "touch-target inline-flex items-center justify-center rounded-[10px] border border-border bg-surface2 p-2 text-muted transition-colors hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:opacity-50";

interface FiltrosHistorial {
  desde: string;
  hasta: string;
  regional: string;
  direccion: string;
  sistema: string;
  nombre: string;
}

const FILTROS_VACIOS: FiltrosHistorial = {
  desde: "",
  hasta: "",
  regional: "",
  direccion: "",
  sistema: "",
  nombre: "",
};

const FILTRO_CLASS =
  "touch-target rounded-[10px] border border-border bg-surface2 px-3 text-sm normal-case text-ink transition-colors focus-visible:border-accent";

export function HistorialRegistros(): JSX.Element {
  const [page, setPage] = useState(0);
  const [filtros, setFiltros] = useState<FiltrosHistorial>(FILTROS_VACIOS);
  const hayFiltros = Object.values(filtros).some((valor) => valor !== "");

  // El nombre se escribe libremente: se aplica con una pequeña espera para no
  // consultar la base en cada tecla.
  const [nombreTexto, setNombreTexto] = useState("");
  useEffect(() => {
    const id = window.setTimeout(() => {
      setPage(0);
      setFiltros((previos) =>
        previos.nombre === nombreTexto.trim() ? previos : { ...previos, nombre: nombreTexto.trim() },
      );
    }, 350);
    return () => window.clearTimeout(id);
  }, [nombreTexto]);

  // Regional y Dirección comparten `jefatura_regional`: elegir una limpia la otra.
  const cambiarFiltro = (cambio: Partial<FiltrosHistorial>): void => {
    setPage(0);
    setFiltros((previos) => ({ ...previos, ...cambio }));
  };
  const limit = 50;
  const [datos, setDatos] = useState<Intervencion[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [editando, setEditando] = useState<Intervencion | null>(null);
  const [guardando, setGuardando] = useState(false);
  const [eliminandoId, setEliminandoId] = useState<number | null>(null);

  const cargar = useCallback(async (): Promise<void> => {
    setLoading(true);
    setError(null);
    try {
      let consulta = supabase.from("intervenciones_diarias").select("*", { count: "exact" });
      if (filtros.desde) consulta = consulta.gte("fecha_consulta", filtros.desde);
      if (filtros.hasta) consulta = consulta.lte("fecha_consulta", filtros.hasta);
      const jefatura = filtros.regional || filtros.direccion;
      if (jefatura) consulta = consulta.eq("jefatura_regional", jefatura);
      if (filtros.sistema) consulta = consulta.eq("sistema_utilizado", filtros.sistema);
      if (filtros.nombre) {
        // Búsqueda parcial sin distinguir mayúsculas; se neutralizan los comodines.
        const literal = filtros.nombre.replace(/[\\%_]/g, (c) => "\\" + c);
        consulta = consulta.ilike("personal_policial", `%${literal}%`);
      }

      const { data, count, error: queryError } = await consulta
        .order("fecha_consulta", { ascending: false })
        .range(page * limit, (page + 1) * limit - 1);

      // Diagnóstico: permite ver en consola la causa real de un "SIN DATOS".
      console.error("Historial intervenciones_diarias", {
        count,
        rows: data?.length,
        error: queryError,
      });

      if (queryError) {
        console.error(queryError);
        setError(queryError.message);
        setDatos([]);
        setTotal(0);
        return;
      }

      setDatos((data ?? []) as Intervencion[]);
      setTotal(typeof count === "number" ? count : 0);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error desconocido al cargar el historial.");
    } finally {
      setLoading(false);
    }
  }, [page, filtros]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  // Recarga inmediata cuando se importan datos desde Excel/CSV.
  useEffect(() => {
    const onRefresh = (): void => {
      void cargar();
    };
    window.addEventListener(INTERVENCIONES_REFRESH_EVENT, onRefresh);
    return () => window.removeEventListener(INTERVENCIONES_REFRESH_EVENT, onRefresh);
  }, [cargar]);

  // Cierra el modal con Escape mientras está abierto.
  useEffect(() => {
    if (!editando) return;
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Escape") setEditando(null);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [editando]);

  // Valores estables por fila para que el formulario se resetee solo al abrir.
  const valoresEdicion = useMemo(
    () => (editando ? aValores(editando) : null),
    [editando],
  );

  const registros = (datos ?? []).slice(0, limit);
  const totalRegistros = total ?? 0;

  const handleEliminar = async (id: number): Promise<void> => {
    if (!window.confirm("¿Seguro que deseas eliminar este registro?")) return;
    setEliminandoId(id);
    setError(null);
    try {
      await eliminarIntervencion(id);
      await cargar();
    } catch (err) {
      void registrarEvento("error_registro", {
        exito: false,
        entidad: "intervenciones_diarias",
        detalle: { contexto: "eliminar", id, mensaje: mensajeDeError(err) },
      });
      setError(err instanceof Error ? err.message : "Error desconocido al eliminar el registro.");
    } finally {
      setEliminandoId(null);
    }
  };

  const handleActualizar = async (payload: IntervencionCreate): Promise<void> => {
    if (!editando) return;
    setGuardando(true);
    setError(null);
    try {
      await actualizarIntervencion(editando.id, payload);
      setEditando(null);
      await cargar();
    } catch (err) {
      void registrarEvento("error_registro", {
        exito: false,
        entidad: "intervenciones_diarias",
        detalle: { contexto: "editar", id: editando.id, mensaje: mensajeDeError(err) },
      });
      setError(err instanceof Error ? err.message : "Error desconocido al actualizar el registro.");
    } finally {
      setGuardando(false);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="font-display text-xl font-semibold uppercase tracking-wide text-ink">
            Historial
          </h2>
          <p className="text-sm text-muted">
            Consulta, edición y borrado de los registros cargados.
          </p>
        </div>
      </div>

      <div
        role="search"
        aria-label="Filtros del historial"
        className="panel flex flex-wrap items-end gap-3"
      >
        <label className="flex flex-col gap-1 text-[11px] uppercase tracking-wide text-muted">
          Desde
          <input
            type="date"
            className={FILTRO_CLASS}
            value={filtros.desde}
            max={filtros.hasta || undefined}
            onChange={(event) => cambiarFiltro({ desde: event.target.value })}
          />
        </label>
        <label className="flex flex-col gap-1 text-[11px] uppercase tracking-wide text-muted">
          Hasta
          <input
            type="date"
            className={FILTRO_CLASS}
            value={filtros.hasta}
            min={filtros.desde || undefined}
            onChange={(event) => cambiarFiltro({ hasta: event.target.value })}
          />
        </label>
        <label className="flex flex-col gap-1 text-[11px] uppercase tracking-wide text-muted">
          Regional
          <select
            className={FILTRO_CLASS}
            value={filtros.regional}
            onChange={(event) => cambiarFiltro({ regional: event.target.value, direccion: "" })}
          >
            <option value="">Todas</option>
            {UNIDADES_REGIONALES.map((unidad) => (
              <option key={unidad} value={unidad}>
                {unidad}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-[11px] uppercase tracking-wide text-muted">
          Dirección
          <select
            className={FILTRO_CLASS}
            value={filtros.direccion}
            onChange={(event) => cambiarFiltro({ direccion: event.target.value, regional: "" })}
          >
            <option value="">Todas</option>
            {DIRECCIONES.map((direccion) => (
              <option key={direccion} value={direccion}>
                {direccion}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-[11px] uppercase tracking-wide text-muted">
          Sistema
          <select
            className={FILTRO_CLASS}
            value={filtros.sistema}
            onChange={(event) => cambiarFiltro({ sistema: event.target.value })}
          >
            <option value="">Todos</option>
            {SISTEMAS_UTILIZADOS.map((sistema) => (
              <option key={sistema} value={sistema}>
                {sistema}
              </option>
            ))}
          </select>
        </label>
        <label className="flex min-w-[220px] flex-1 flex-col gap-1 text-[11px] uppercase tracking-wide text-muted">
          Personal policial
          <input
            type="search"
            className={FILTRO_CLASS}
            placeholder="Buscar por nombre…"
            value={nombreTexto}
            onChange={(event) => setNombreTexto(event.target.value)}
          />
        </label>
        {hayFiltros || nombreTexto ? (
          <button
            type="button"
            onClick={() => {
              setNombreTexto("");
              cambiarFiltro(FILTROS_VACIOS);
            }}
            className="touch-target rounded-[10px] border border-border bg-surface2 px-4 text-xs font-semibold uppercase tracking-wide text-ink transition-colors hover:border-accent hover:text-accent"
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

      {!error && loading ? (
        <p
          role="status"
          className="panel flex items-center justify-center py-10 text-sm text-muted"
        >
          Cargando registros…
        </p>
      ) : !error && registros.length === 0 ? (
        <p
          role="status"
          className="panel flex items-center justify-center py-10 text-sm text-muted"
        >
          SIN DATOS
        </p>
      ) : error ? null : (
        <div className="panel overflow-x-auto p-0">
          <table data-testid="historial-tabla" className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-border text-left text-[11px] uppercase tracking-wide text-muted">
                <th className="px-4 py-3 font-medium">Fecha</th>
                <th className="px-4 py-3 font-medium">Regional</th>
                <th className="px-4 py-3 font-medium">Dependencia</th>
                <th className="px-4 py-3 font-medium">Tipo Consulta</th>
                <th className="px-4 py-3 font-medium">Resultado</th>
                <th className="px-4 py-3 font-medium">Sistema</th>
                <th className="px-4 py-3 font-medium">Devuelto</th>
                <th className="px-4 py-3 text-right font-medium">Acciones</th>
              </tr>
            </thead>
            <tbody>
              {registros.map((registro) => (
                <tr
                  key={registro.id}
                  data-devuelto={registro.tramite_devuelto === "No" ? "no" : undefined}
                  className={`border-b border-border/60 last:border-b-0 ${
                    registro.tramite_devuelto === "No"
                      ? "bg-[color-mix(in_srgb,var(--warn)_30%,transparent)] shadow-[inset_3px_0_0_var(--warn)]"
                      : ""
                  }`}
                >
                  <td className="px-4 py-3 text-ink2">{registro.fecha_consulta ?? "—"}</td>
                  <td className="px-4 py-3 text-ink2">{registro.jefatura_regional || "—"}</td>
                  <td className="px-4 py-3 text-ink2">{registro.dependencia || "—"}</td>
                  <td className="px-4 py-3 text-ink2">{registro.tipo_consulta || "—"}</td>
                  <td className="px-4 py-3 text-ink2">{registro.resultado_consulta || "—"}</td>
                  <td className="px-4 py-3 text-ink2">{registro.sistema_utilizado || "—"}</td>
                  <td className="px-4 py-3 text-ink2">{registro.tramite_devuelto || "—"}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        type="button"
                        aria-label={`Editar registro ${registro.id}`}
                        onClick={() => setEditando(registro)}
                        className={ACTION_BUTTON_CLASS}
                      >
                        <Pencil size={16} aria-hidden="true" />
                      </button>
                      <button
                        type="button"
                        aria-label={`Eliminar registro ${registro.id}`}
                        disabled={eliminandoId === registro.id}
                        onClick={() => void handleEliminar(registro.id)}
                        className={ACTION_BUTTON_CLASS}
                      >
                        <Trash2 size={16} aria-hidden="true" />
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {!loading && totalRegistros > 0 ? (
        <nav
          aria-label="Paginación del historial"
          className="flex items-center justify-between gap-4"
        >
          <button
            type="button"
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className={ACTION_BUTTON_CLASS}
          >
            <ChevronLeft size={16} aria-hidden="true" />
            Anterior
          </button>
          <p className="text-sm text-muted">
            Mostrando {page * limit + 1}–{page * limit + registros.length} de {totalRegistros}
          </p>
          <button
            type="button"
            onClick={() => setPage((p) => p + 1)}
            disabled={page * limit + registros.length >= totalRegistros}
            className={ACTION_BUTTON_CLASS}
          >
            Siguiente
            <ChevronRight size={16} aria-hidden="true" />
          </button>
        </nav>
      ) : null}

      {editando && valoresEdicion
        ? createPortal(
        <div
          className="fixed inset-0 z-50 overflow-y-auto bg-night/70 backdrop-blur-sm"
          onClick={() => setEditando(null)}
          role="presentation"
          data-testid="historial-modal"
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Editar registro"
            className="panel min-h-full w-full rounded-none"
            onClick={(event) => event.stopPropagation()}
          >
            <div className="mb-4 flex items-center justify-between gap-3">
              <h3 className="font-display text-lg font-semibold uppercase tracking-wide text-ink">
                Editar registro
              </h3>
              <button
                type="button"
                aria-label="Cerrar"
                onClick={() => setEditando(null)}
                className={ACTION_BUTTON_CLASS}
              >
                <X size={18} aria-hidden="true" />
              </button>
            </div>
            <FormularioIntervencion
              valoresIniciales={valoresEdicion}
              onSubmit={handleActualizar}
              enviando={guardando}
              textoBoton="Guardar cambios"
            />
          </div>
        </div>,
        document.body,
      )
        : null}
    </div>
  );
}
