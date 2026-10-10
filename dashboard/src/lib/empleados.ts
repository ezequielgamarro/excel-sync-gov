/**
 * Productividad por empleado (a partir de `resumen_empleados`, que agrega la
 * auditoría). Funciones puras, sin acceso a red.
 *
 * - Cargados: registros dados de alta (individuales o por importación).
 * - Errores: intentos fallidos (al guardar, importar o exportar).
 * - Correcciones: ediciones + eliminaciones de registros.
 * - Tasa de error: errores / (cargados + errores).
 */

export interface ResumenEmpleadoFila {
  usuario_email: string;
  rol: string;
  registros_cargados: number | string;
  ediciones: number | string;
  eliminaciones: number | string;
  importaciones: number | string;
  errores: number | string;
  eventos: number | string;
  ultimo_evento: string | null;
}

export interface Empleado {
  email: string;
  nombre: string;
  rol: string;
  cargados: number;
  ediciones: number;
  eliminaciones: number;
  correcciones: number;
  importaciones: number;
  errores: number;
  eventos: number;
  tasaError: number;
  ultimoEvento: string | null;
}

const ROLES_PERSONAS = new Set(["empleado", "admin"]);

/** Parte local del email, para etiquetas cortas en los gráficos. */
export function nombreCorto(email: string): string {
  const local = email.split("@")[0] ?? email;
  return local || email;
}

function n(valor: number | string): number {
  const x = Number(valor);
  return Number.isFinite(x) ? x : 0;
}

/** Solo personas (empleados y admins); excluye `apps-script`/sistema y visitantes. */
export function aEmpleados(filas: readonly ResumenEmpleadoFila[]): Empleado[] {
  return filas
    .filter((f) => ROLES_PERSONAS.has(f.rol))
    .map((f) => {
      const cargados = n(f.registros_cargados);
      const errores = n(f.errores);
      const ediciones = n(f.ediciones);
      const eliminaciones = n(f.eliminaciones);
      const base = cargados + errores;
      return {
        email: f.usuario_email,
        nombre: nombreCorto(f.usuario_email),
        rol: f.rol,
        cargados,
        ediciones,
        eliminaciones,
        correcciones: ediciones + eliminaciones,
        importaciones: n(f.importaciones),
        errores,
        eventos: n(f.eventos),
        tasaError: base > 0 ? (errores / base) * 100 : 0,
        ultimoEvento: f.ultimo_evento,
      };
    });
}

/** Empleado con el mayor valor de `clave` (null si nadie supera 0). */
export function maximoPor(
  empleados: readonly Empleado[],
  clave: "cargados" | "errores" | "correcciones",
): Empleado | null {
  let mejor: Empleado | null = null;
  for (const e of empleados) {
    if (e[clave] > 0 && (mejor === null || e[clave] > mejor[clave])) mejor = e;
  }
  return mejor;
}

export function ordenarPor(
  empleados: readonly Empleado[],
  clave: "cargados" | "errores" | "correcciones" | "tasaError",
): Empleado[] {
  return [...empleados].sort((a, b) => b[clave] - a[clave] || a.nombre.localeCompare(b.nombre));
}
