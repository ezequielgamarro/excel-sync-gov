/**
 * `importarIntervenciones` — lectura/mapeo de filas Excel/CSV al formato de la
 * tabla `intervenciones_diarias`. Cubre el mapeo de cabeceras en español y
 * snake_case, la normalización de fecha/hora, el descarte de columnas no
 * reconocidas y de filas vacías.
 */

import { describe, expect, it } from "vitest";
import {
  normalizarFilaImportada,
  normalizarFilasImportadas,
} from "./importarIntervenciones";

const FILA_ESPANOL: Record<string, unknown> = {
  "Fecha Consulta": "15/10/2026",
  "Hora Consulta": "14:30:00",
  Jerarquía: "Oficial",
  "Personal Policial": "Juan Pérez",
  "Jefatura Regional": "U.R. Norte",
  Dependencias: "Comisaría 1",
  "Tipo Consulta": "Antecedentes",
  Identificación: "12345678",
  "Tipo de arma/vehiculo": "Arma",
  Resultado: "POSITIVO",
  "Causas Penales": "Robo",
  "Registro/Legajo": "999",
  "Autoridad Judicial": "Juzgado 1",
  "Sistema Utilizado": "SIGI",
  "Trámite Devuelto": "SI",
  "Hora Resp": "15:45:10",
  "Personal que informa": "Ana",
  Cargo: "Sargento",
  "Operativos Preventivos": "2",
  Allanamiento: "NO",
  "Mini reseña": "Texto breve",
  id: 5,
  turno: "mañana",
  desconocido: "descartar",
};

describe("normalizarFilaImportada", () => {
  it("mapea cabeceras en español a las columnas exactas de la tabla", () => {
    const fila = normalizarFilaImportada(FILA_ESPANOL);
    expect(fila).not.toBeNull();
    expect(fila).toMatchObject({
      fecha_consulta: "2026-10-15",
      hora_consulta: "14:30",
      jerarquia: "Oficial",
      personal_policial: "Juan Pérez",
      jefatura_regional: "U.R. Norte",
      dependencia: "Comisaría 1",
      tipo_consulta: "Antecedentes",
      identificacion: "12345678",
      detalle_tipo: "Arma",
      resultado_consulta: "POSITIVO",
      causas: "Robo",
      numero_registro: "999",
      autoridad_judicial: "Juzgado 1",
      sistema_utilizado: "SIGI",
      tramite_devuelto: "SI",
      hora_respuesta: "15:45",
      personal_informa: "Ana",
      cargo_informa: "Sargento",
      operativo_preventivo: "2",
      allanamiento: "NO",
      mini_resena: "Texto breve",
    });
  });

  it("descarta cabeceras no reconocidas (id, turno, desconocido)", () => {
    const fila = normalizarFilaImportada(FILA_ESPANOL);
    expect(fila).not.toBeNull();
    expect(fila).not.toHaveProperty("id");
    expect(fila).not.toHaveProperty("turno");
    expect(fila).not.toHaveProperty("desconocido");
  });

  it("acepta las cabeceras snake_case de la tabla (reimportar lo exportado)", () => {
    const fila = normalizarFilaImportada({
      fecha_consulta: "2026-10-15",
      resultado_consulta: "NEGATIVO",
      detalle_tipo: "Vehiculo",
      numero_registro: 4242,
      hora_respuesta: "09:05",
    });
    expect(fila).toMatchObject({
      fecha_consulta: "2026-10-15",
      resultado_consulta: "NEGATIVO",
      detalle_tipo: "Vehiculo",
      numero_registro: "4242",
      hora_respuesta: "09:05",
    });
  });

  it("devuelve null para una fila totalmente vacía", () => {
    expect(normalizarFilaImportada({})).toBeNull();
    expect(normalizarFilaImportada({ id: 1, turno: "noche" })).toBeNull();
  });

  it("normaliza fechas alternativas y deja la hora inválida tal cual", () => {
    const barra = normalizarFilaImportada({ "Fecha Consulta": "1/2/2026" });
    expect(barra?.fecha_consulta).toBe("2026-02-01");
    const guion = normalizarFilaImportada({ "Fecha Consulta": "05-12-2026" });
    expect(guion?.fecha_consulta).toBe("2026-12-05");
    const invalida = normalizarFilaImportada({
      "Fecha Consulta": "no es fecha",
      Dependencias: "Comisaría 3",
    });
    expect(invalida?.fecha_consulta).toBe("");
    const hora = normalizarFilaImportada({ "Hora Consulta": "sin hora" });
    expect(hora?.hora_consulta).toBe("sin hora");
  });
});

describe("normalizarFilasImportadas", () => {
  it("omite las filas vacías y conserva sólo las válidas", () => {
    const filas = normalizarFilasImportadas([
      FILA_ESPANOL,
      {},
      { "Fecha Consulta": "", Dependencias: "" },
      { Dependencias: "Comisaría 2" },
    ]);
    expect(filas).toHaveLength(2);
    expect(filas[0].dependencia).toBe("Comisaría 1");
    expect(filas[1].dependencia).toBe("Comisaría 2");
  });
});
