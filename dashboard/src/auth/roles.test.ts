import { describe, expect, it } from "vitest";
import { rolDeRoles, seccionInicial, seccionPermitida } from "./roles";

describe("roles", () => {
  it("platform-admin es admin; empleado y visitante se reconocen", () => {
    expect(rolDeRoles(["platform-admin", "viewer"])).toBe("admin");
    expect(rolDeRoles(["empleado"])).toBe("empleado");
    expect(rolDeRoles(["visitante"])).toBe("visitante");
  });

  it("sin rol reconocido se asume el menos privilegiado", () => {
    expect(rolDeRoles(undefined)).toBe("visitante");
    expect(rolDeRoles([])).toBe("visitante");
  });

  it("el empleado accede a carga, historial y monitor, nada más", () => {
    expect(seccionPermitida("empleado", "carga")).toBe(true);
    expect(seccionPermitida("empleado", "historial")).toBe(true);
    expect(seccionPermitida("empleado", "monitor")).toBe(true);
    expect(seccionPermitida("empleado", "auditoria")).toBe(false);
    expect(seccionPermitida("empleado", "empleados")).toBe(false);
    expect(seccionPermitida("empleado", "resumen")).toBe(false);
    expect(seccionPermitida("empleado", "usuarios")).toBe(false);
    expect(seccionInicial("empleado")).toBe("carga");
  });

  it("el visitante solo accede al monitor y el admin a usuarios", () => {
    expect(seccionPermitida("visitante", "monitor")).toBe(true);
    expect(seccionPermitida("visitante", "historial")).toBe(false);
    expect(seccionPermitida("admin", "usuarios")).toBe(true);
    expect(seccionInicial("visitante")).toBe("monitor");
  });
});
