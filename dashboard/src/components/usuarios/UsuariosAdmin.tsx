/**
 * Pestaña «Usuarios» (solo administradores): alta, cambio de rol/contraseña y
 * baja de usuarios. Todo pasa por la Edge Function `admin-users`, que valida en
 * el servidor que quien llama es `platform-admin` (la service role nunca llega
 * al navegador).
 */

import { useCallback, useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Trash2 } from "lucide-react";
import { supabase } from "../../supabaseClient";
import { ROL_ETIQUETA } from "../../auth/roles";
import type { Rol } from "../../auth/roles";

interface UsuarioFila {
  id: string;
  email: string;
  rol: Rol;
  created_at: string;
  last_sign_in_at: string | null;
}

const ROLES: readonly Rol[] = ["admin", "empleado", "visitante"];

const DESCRIPCION_ROL: Record<Rol, string> = {
  admin: "Acceso total, incluida la gestión de usuarios.",
  empleado: "Carga de Datos, Historial y Monitor (sin exportar a Excel).",
  visitante: "Solo la vista Monitor: todos los gráficos con filtros.",
};

const INPUT_CLASS =
  "touch-target rounded-[10px] border border-border bg-surface2 px-3 text-sm normal-case text-ink transition-colors focus-visible:border-accent";

async function llamar<T>(body: Record<string, unknown>): Promise<T> {
  const { data, error } = await supabase.functions.invoke("admin-users", { body });
  if (error) {
    // En errores HTTP, `context` es la Response con `{ error }` en JSON.
    const respuesta = (error as { context?: Response }).context;
    if (respuesta && typeof respuesta.json === "function") {
      let mensaje: string | undefined;
      try {
        mensaje = ((await respuesta.json()) as { error?: string }).error;
      } catch {
        mensaje = undefined;
      }
      if (mensaje) throw new Error(mensaje);
    }
    throw new Error(error.message);
  }
  return data as T;
}

function formatearFecha(iso: string | null): string {
  if (!iso) return "—";
  const fecha = new Date(iso);
  return Number.isNaN(fecha.getTime()) ? "—" : fecha.toLocaleString("es-AR");
}

export function UsuariosAdmin({ miId }: { miId: string }): JSX.Element {
  const [usuarios, setUsuarios] = useState<UsuarioFila[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [rol, setRol] = useState<Rol>("empleado");

  const cargar = useCallback(async (): Promise<void> => {
    setCargando(true);
    try {
      const { users } = await llamar<{ users: UsuarioFila[] }>({ action: "list" });
      setUsuarios(users);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo cargar la lista de usuarios.");
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  const ejecutar = async (accion: () => Promise<unknown>, exito: string): Promise<boolean> => {
    setGuardando(true);
    setError(null);
    setAviso(null);
    try {
      await accion();
      setAviso(exito);
      await cargar();
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Error desconocido.");
      return false;
    } finally {
      setGuardando(false);
    }
  };

  const handleCrear = async (event: FormEvent): Promise<void> => {
    event.preventDefault();
    const ok = await ejecutar(
      () => llamar({ action: "create", email, password, rol }),
      `Usuario ${email.trim().toLowerCase()} creado como ${ROL_ETIQUETA[rol]}.`,
    );
    if (ok) {
      setEmail("");
      setPassword("");
    }
  };

  const handleCambiarRol = (usuario: UsuarioFila, nuevo: Rol): Promise<boolean> =>
    ejecutar(
      () => llamar({ action: "update", id: usuario.id, rol: nuevo }),
      `${usuario.email} ahora es ${ROL_ETIQUETA[nuevo]}. El cambio se aplica en su próximo inicio de sesión.`,
    );

  const handleCambiarPassword = async (usuario: UsuarioFila): Promise<void> => {
    const nueva = window.prompt(`Nueva contraseña para ${usuario.email} (mínimo 8 caracteres):`);
    if (!nueva) return;
    await ejecutar(
      () => llamar({ action: "update", id: usuario.id, password: nueva }),
      `Contraseña de ${usuario.email} actualizada.`,
    );
  };

  const handleEliminar = async (usuario: UsuarioFila): Promise<void> => {
    if (!window.confirm(`¿Eliminar al usuario ${usuario.email}? Esta acción no se puede deshacer.`)) {
      return;
    }
    await ejecutar(
      () => llamar({ action: "delete", id: usuario.id }),
      `Usuario ${usuario.email} eliminado.`,
    );
  };

  return (
    <div className="flex flex-col gap-6" data-testid="usuarios-admin">
      <div>
        <h2 className="font-display text-xl font-semibold uppercase tracking-wide text-ink">
          Usuarios
        </h2>
        <p className="text-sm text-muted">
          Creá usuarios y asignales un rol. Cada rol define qué ve y qué puede hacer.
        </p>
      </div>

      {error ? (
        <p
          role="alert"
          className="rounded-[12px] border border-neg/50 bg-neg/10 px-4 py-3 text-sm font-semibold text-neg"
        >
          {error}
        </p>
      ) : null}
      {aviso ? (
        <p
          role="status"
          className="rounded-[12px] border border-border-strong bg-surface2 px-4 py-3 text-sm font-semibold text-ink"
        >
          {aviso}
        </p>
      ) : null}

      <form
        onSubmit={(event) => void handleCrear(event)}
        className="panel flex flex-wrap items-end gap-3"
        aria-label="Crear usuario"
      >
        <label className="flex min-w-[220px] flex-1 flex-col gap-1 text-[11px] uppercase tracking-wide text-muted">
          Email
          <input
            type="email"
            required
            autoComplete="off"
            className={INPUT_CLASS}
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </label>
        <label className="flex min-w-[200px] flex-1 flex-col gap-1 text-[11px] uppercase tracking-wide text-muted">
          Contraseña (mín. 8)
          <input
            type="password"
            required
            minLength={8}
            autoComplete="new-password"
            className={INPUT_CLASS}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1 text-[11px] uppercase tracking-wide text-muted">
          Rol
          <select
            className={INPUT_CLASS}
            value={rol}
            onChange={(event) => setRol(event.target.value as Rol)}
          >
            {ROLES.map((r) => (
              <option key={r} value={r}>
                {ROL_ETIQUETA[r]}
              </option>
            ))}
          </select>
        </label>
        <button
          type="submit"
          disabled={guardando}
          className="touch-target rounded-[10px] border border-accent/60 bg-accent-soft px-5 text-xs font-semibold uppercase tracking-wide text-accent transition-colors hover:border-accent disabled:cursor-not-allowed disabled:opacity-50"
        >
          {guardando ? "Guardando…" : "Crear usuario"}
        </button>
        <p className="w-full text-xs text-muted">{DESCRIPCION_ROL[rol]}</p>
      </form>

      <div className="panel overflow-x-auto p-0">
        <table className="w-full border-collapse text-sm">
          <thead>
            <tr className="border-b border-border text-left text-[11px] uppercase tracking-wide text-muted">
              <th className="px-4 py-3 font-medium">Email</th>
              <th className="px-4 py-3 font-medium">Rol</th>
              <th className="px-4 py-3 font-medium">Creado</th>
              <th className="px-4 py-3 font-medium">Último acceso</th>
              <th className="px-4 py-3 text-right font-medium">Acciones</th>
            </tr>
          </thead>
          <tbody>
            {cargando && usuarios.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-muted">
                  Cargando usuarios…
                </td>
              </tr>
            ) : null}
            {usuarios.map((usuario) => {
              const esYo = usuario.id === miId;
              return (
                <tr key={usuario.id} className="border-b border-border/60 last:border-b-0">
                  <td className="px-4 py-3 text-ink2">
                    {usuario.email}
                    {esYo ? <span className="ml-2 text-xs text-muted">(vos)</span> : null}
                  </td>
                  <td className="px-4 py-3">
                    <select
                      aria-label={`Rol de ${usuario.email}`}
                      className={INPUT_CLASS}
                      value={usuario.rol}
                      disabled={guardando || esYo}
                      onChange={(event) =>
                        void handleCambiarRol(usuario, event.target.value as Rol)
                      }
                    >
                      {ROLES.map((r) => (
                        <option key={r} value={r}>
                          {ROL_ETIQUETA[r]}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-4 py-3 text-ink2">{formatearFecha(usuario.created_at)}</td>
                  <td className="px-4 py-3 text-ink2">{formatearFecha(usuario.last_sign_in_at)}</td>
                  <td className="px-4 py-3">
                    <div className="flex items-center justify-end gap-2">
                      <button
                        type="button"
                        disabled={guardando}
                        onClick={() => void handleCambiarPassword(usuario)}
                        className="touch-target rounded-[10px] border border-border bg-surface2 px-3 text-xs font-semibold text-ink2 transition-colors hover:border-accent hover:text-accent disabled:opacity-50"
                      >
                        Cambiar contraseña
                      </button>
                      <button
                        type="button"
                        aria-label={`Eliminar ${usuario.email}`}
                        disabled={guardando || esYo}
                        onClick={() => void handleEliminar(usuario)}
                        className="touch-target inline-flex items-center justify-center rounded-[10px] border border-border bg-surface2 p-2 text-muted transition-colors hover:border-neg hover:text-neg disabled:cursor-not-allowed disabled:opacity-40"
                      >
                        <Trash2 size={16} aria-hidden="true" />
                      </button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
