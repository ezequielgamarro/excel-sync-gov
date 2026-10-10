/**
 * Roles de la aplicación (se leen de `app_metadata.roles` del JWT de Supabase):
 * - admin: `platform-admin`. Todo, incluida la gestión de usuarios, la auditoría
 *   y la productividad de empleados.
 * - empleado: «Carga de Datos», «Historial» y la vista «Monitor».
 * - visitante: solo la vista «Monitor» (todos los gráficos con filtros).
 * Sin rol reconocido se asume el menos privilegiado (visitante).
 */

import type { AuthSession } from "./session";

export type Rol = "admin" | "empleado" | "visitante";

export function rolDeRoles(roles: readonly string[] | undefined): Rol {
  const lista = roles ?? [];
  if (lista.includes("platform-admin")) return "admin";
  if (lista.includes("empleado")) return "empleado";
  return "visitante";
}

export function rolDeSesion(session: AuthSession | null): Rol {
  return rolDeRoles(session?.roles);
}

export const ROL_ETIQUETA: Record<Rol, string> = {
  admin: "Administrador",
  empleado: "Empleado",
  visitante: "Visitante",
};

/** Secciones del menú visibles por rol (el orden es el del menú). */
export const SECCIONES_POR_ROL: Record<Rol, readonly string[]> = {
  admin: [
    "resumen",
    "logistica",
    "incidentes",
    "comparativas",
    "estadisticas",
    "carga",
    "historial",
    "empleados",
    "auditoria",
    "usuarios",
  ],
  empleado: ["carga", "historial", "monitor"],
  visitante: ["monitor"],
};

export function seccionPermitida(rol: Rol, id: string): boolean {
  return id === "ayuda" || SECCIONES_POR_ROL[rol].includes(id);
}

export function seccionInicial(rol: Rol): string {
  return SECCIONES_POR_ROL[rol][0];
}
