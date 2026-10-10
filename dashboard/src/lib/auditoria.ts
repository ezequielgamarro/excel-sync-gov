/**
 * Auditoría del sistema (lado cliente).
 *
 * Los movimientos sobre `intervenciones_diarias` (crear/editar/eliminar) los
 * registra la base con triggers. Aquí se registran los eventos que solo el
 * navegador conoce: login, logout, importar/exportar Excel, imprimir PDF y
 * errores al guardar. El servidor fija usuario, email y rol desde el JWT, así
 * que lo enviado acá no puede suplantar a otra persona. Nunca rompe la UI.
 */

import { supabase } from "../supabaseClient";

export type AccionCliente =
  | "login"
  | "logout"
  | "importar_excel"
  | "exportar_excel"
  | "imprimir_pdf"
  | "error_registro";

export interface OpcionesEvento {
  exito?: boolean;
  entidad?: string;
  detalle?: Record<string, unknown>;
}

export async function registrarEvento(
  accion: AccionCliente,
  opciones: OpcionesEvento = {},
): Promise<void> {
  try {
    await supabase.from("auditoria_eventos").insert({
      accion,
      exito: opciones.exito ?? true,
      entidad: opciones.entidad ?? "",
      detalle: opciones.detalle ?? {},
    });
  } catch {
    /* la auditoría nunca debe interrumpir la operación del usuario */
  }
}

/** Texto corto y seguro del error (sin volcar objetos enteros). */
export function mensajeDeError(err: unknown): string {
  return (err instanceof Error ? err.message : String(err)).slice(0, 300);
}
