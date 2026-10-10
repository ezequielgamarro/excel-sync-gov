import { describe, expect, it } from "vitest";
import { aEmpleados, maximoPor, ordenarPor, type ResumenEmpleadoFila } from "./empleados";
import { describirEvento, type EventoAuditoria } from "./auditoriaTexto";

const fila = (over: Partial<ResumenEmpleadoFila>): ResumenEmpleadoFila => ({
  usuario_email: "ana@x.com",
  rol: "empleado",
  registros_cargados: 0,
  ediciones: 0,
  eliminaciones: 0,
  importaciones: 0,
  errores: 0,
  eventos: 0,
  ultimo_evento: null,
  ...over,
});

describe("empleados", () => {
  it("excluye sistema y visitantes y convierte los bigint llegados como texto", () => {
    const lista = aEmpleados([
      fila({ usuario_email: "ana@x.com", registros_cargados: "30", errores: "10" }),
      fila({ usuario_email: "apps-script", rol: "sistema", registros_cargados: 500 }),
      fila({ usuario_email: "v@x.com", rol: "visitante" }),
    ]);
    expect(lista).toHaveLength(1);
    expect(lista[0].cargados).toBe(30);
    expect(lista[0].nombre).toBe("ana");
    expect(lista[0].tasaError).toBeCloseTo(25);
  });

  it("calcula el máximo y ordena; sin actividad no hay máximo", () => {
    const lista = aEmpleados([
      fila({ usuario_email: "a@x.com", registros_cargados: 5, errores: 3 }),
      fila({ usuario_email: "b@x.com", registros_cargados: 9, errores: 1 }),
    ]);
    expect(maximoPor(lista, "cargados")?.email).toBe("b@x.com");
    expect(maximoPor(lista, "errores")?.email).toBe("a@x.com");
    expect(ordenarPor(lista, "errores")[0].email).toBe("a@x.com");
    expect(maximoPor(aEmpleados([fila({})]), "errores")).toBeNull();
  });
});

describe("describirEvento", () => {
  const base: EventoAuditoria = {
    id: 1,
    created_at: "2026-10-10T10:00:00Z",
    usuario_id: null,
    usuario_email: "ana@x.com",
    rol: "empleado",
    accion: "editar_registro",
    entidad: "intervenciones_diarias",
    entidad_id: "7",
    detalle: { cambios: { jerarquia: { antes: "x", despues: "y" } } },
    exito: true,
  };

  it("explica qué campo cambió", () => {
    expect(describirEvento(base)).toContain("Jerarquía: «x» → «y»");
  });

  it("describe cargas masivas y errores", () => {
    expect(
      describirEvento({
        ...base,
        accion: "crear_registro",
        detalle: { cantidad: 120, id_desde: 1, id_hasta: 120 },
      }),
    ).toContain("120 registros");
    expect(
      describirEvento({
        ...base,
        accion: "error_registro",
        exito: false,
        detalle: { contexto: "crear", mensaje: "boom" },
      }),
    ).toContain("boom");
  });
});
