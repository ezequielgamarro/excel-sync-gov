/**
 * Textos en español para los eventos de auditoría (qué hizo cada persona).
 */

export interface EventoAuditoria {
  id: number;
  created_at: string;
  usuario_id: string | null;
  usuario_email: string;
  rol: string;
  accion: string;
  entidad: string;
  entidad_id: string;
  detalle: Record<string, unknown>;
  exito: boolean;
}

export const ACCION_ETIQUETA: Record<string, string> = {
  login: "Inicio de sesión",
  logout: "Cierre de sesión",
  crear_registro: "Carga de registros",
  editar_registro: "Edición de registro",
  eliminar_registro: "Eliminación de registro",
  importar_excel: "Importación de Excel",
  exportar_excel: "Exportación a Excel",
  imprimir_pdf: "Impresión / PDF",
  error_registro: "Error al guardar",
  crear_usuario: "Alta de usuario",
  editar_usuario: "Cambio de usuario",
  eliminar_usuario: "Baja de usuario",
};

export const ACCIONES = Object.keys(ACCION_ETIQUETA);

const CAMPO_ETIQUETA: Record<string, string> = {
  fecha_consulta: "Fecha consulta",
  hora_consulta: "Hora consulta",
  jerarquia: "Jerarquía",
  personal_policial: "Personal policial",
  jefatura_regional: "Jefatura regional",
  dependencia: "Dependencia",
  tipo_consulta: "Tipo consulta",
  identificacion: "Identificación",
  detalle_tipo: "Tipo de arma/vehículo",
  resultado_consulta: "Resultado",
  causas: "Causas penales",
  numero_registro: "N° de registro",
  autoridad_judicial: "Autoridad judicial",
  sistema_utilizado: "Sistema utilizado",
  tramite_devuelto: "Trámite devuelto",
  hora_respuesta: "Hora respuesta",
  personal_informa: "Personal que informa",
  cargo_informa: "Cargo",
  operativo_preventivo: "Operativos preventivos",
  allanamiento: "Allanamiento",
  mini_resena: "Mini reseña",
  legajo: "Legajo",
  lugar_hecho: "Lugar del hecho",
  detalle_identificacion: "Detalle de identificación",
};

function texto(valor: unknown): string {
  if (valor === null || valor === undefined || valor === "") return "vacío";
  return String(valor).slice(0, 60);
}

function num(valor: unknown): number {
  const n = Number(valor);
  return Number.isFinite(n) ? n : 0;
}

/** Frase corta que explica qué hizo la persona en este evento. */
export function describirEvento(evento: EventoAuditoria): string {
  const d = evento.detalle ?? {};
  switch (evento.accion) {
    case "login":
      return "Ingresó al sistema.";
    case "logout":
      return "Cerró su sesión.";
    case "crear_registro": {
      const n = num(d.cantidad);
      return n > 1
        ? `Cargó ${n} registros (N.º ${texto(d.id_desde)} a ${texto(d.id_hasta)}).`
        : `Cargó el registro N.º ${texto(evento.entidad_id)}.`;
    }
    case "editar_registro": {
      const cambios = (d.cambios ?? {}) as Record<string, { antes?: unknown; despues?: unknown }>;
      const partes = Object.entries(cambios)
        .slice(0, 4)
        .map(
          ([campo, v]) =>
            `${CAMPO_ETIQUETA[campo] ?? campo}: «${texto(v.antes)}» → «${texto(v.despues)}»`,
        );
      const extra = Object.keys(cambios).length - partes.length;
      return `Editó el registro N.º ${evento.entidad_id}. ${partes.join("; ")}${
        extra > 0 ? ` (+${extra} más)` : ""
      }`;
    }
    case "eliminar_registro": {
      const r = (d.registro ?? {}) as Record<string, unknown>;
      return `Eliminó el registro N.º ${evento.entidad_id} (${texto(r.fecha_consulta)}, ${texto(
        r.personal_policial,
      )}).`;
    }
    case "importar_excel":
      return evento.exito
        ? `Importó ${num(d.registros)} registros desde «${texto(d.archivo)}».`
        : `Falló la importación de «${texto(d.archivo)}»: ${texto(d.mensaje)}`;
    case "exportar_excel":
      return evento.exito
        ? `Exportó el reporte a Excel (${texto(d.unidad)}, ${texto(d.rango)}).`
        : `Falló la exportación a Excel: ${texto(d.mensaje)}`;
    case "imprimir_pdf":
      return `Imprimió o guardó como PDF la sección ${texto(d.seccion)}.`;
    case "error_registro":
      return `Error al ${texto(d.contexto)} un registro: ${texto(d.mensaje)}`;
    case "crear_usuario":
      return `Creó el usuario ${texto(d.email)} con rol ${texto(d.rol)}.`;
    case "editar_usuario":
      return `Modificó al usuario ${texto(d.email)}${d.rol ? ` (nuevo rol: ${texto(d.rol)})` : ""}${
        d.password ? " (cambió la contraseña)" : ""
      }.`;
    case "eliminar_usuario":
      return `Eliminó al usuario ${texto(d.email)}.`;
    default:
      return ACCION_ETIQUETA[evento.accion] ?? evento.accion;
  }
}
