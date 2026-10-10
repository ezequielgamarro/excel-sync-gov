/**
 * `BotonImportarExcel` — botón que lee un Excel/CSV y lo inserta en Supabase.
 * Verifica el flujo feliz (importa + alert de éxito + evento de refresco), el
 * caso sin filas válidas y el error.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

const mocks = vi.hoisted(() => ({
  leerArchivoIntervenciones: vi.fn(),
  importarIntervenciones: vi.fn(),
}));

vi.mock("../../data/importarIntervenciones", async () => {
  const actual = await vi.importActual<typeof import("../../data/importarIntervenciones")>(
    "../../data/importarIntervenciones",
  );
  return {
    ...actual,
    leerArchivoIntervenciones: mocks.leerArchivoIntervenciones,
    importarIntervenciones: mocks.importarIntervenciones,
  };
});

import { BotonImportarExcel } from "./BotonImportarExcel";
import { INTERVENCIONES_REFRESH_EVENT } from "../../data/importarIntervenciones";

function seleccionarArchivo(): void {
  const input = screen.getByTestId("input-importar-excel") as HTMLInputElement;
  const file = new File(["contenido"], "datos.xlsx", {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  fireEvent.change(input, { target: { files: [file] } });
}

describe("BotonImportarExcel", () => {
  let alertSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    mocks.leerArchivoIntervenciones.mockReset();
    mocks.importarIntervenciones.mockReset();
    alertSpy = vi.fn();
    vi.stubGlobal("alert", alertSpy);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("muestra el botón «Importar Datos» y un input que acepta xlsx/xls/csv", () => {
    render(<BotonImportarExcel />);
    expect(screen.getByTestId("boton-importar-excel")).toHaveTextContent("Importar Datos");
    const input = screen.getByTestId("input-importar-excel");
    expect(input).toHaveAttribute("accept", ".xlsx, .xls, .csv");
  });

  it("importa las filas, avisa y emite el evento de refresco", async () => {
    mocks.leerArchivoIntervenciones.mockResolvedValue([{ fecha_consulta: "2026-10-15" }]);
    mocks.importarIntervenciones.mockResolvedValue(1);

    const listener = vi.fn();
    window.addEventListener(INTERVENCIONES_REFRESH_EVENT, listener);

    render(<BotonImportarExcel />);
    seleccionarArchivo();

    await waitFor(() => expect(mocks.importarIntervenciones).toHaveBeenCalledTimes(1));
    expect(mocks.leerArchivoIntervenciones).toHaveBeenCalledTimes(1);
    expect(alertSpy).toHaveBeenCalledWith("Se importaron 1 registros correctamente");
    await waitFor(() => expect(listener).toHaveBeenCalledTimes(1));

    window.removeEventListener(INTERVENCIONES_REFRESH_EVENT, listener);
  });

  it("avisa y no inserta cuando no hay filas válidas", async () => {
    mocks.leerArchivoIntervenciones.mockResolvedValue([]);

    render(<BotonImportarExcel />);
    seleccionarArchivo();

    await waitFor(() => expect(alertSpy).toHaveBeenCalled());
    expect(alertSpy).toHaveBeenCalledWith("No se encontraron filas válidas para importar.");
    expect(mocks.importarIntervenciones).not.toHaveBeenCalled();
  });

  it("avisa por window.alert si la lectura/importación falla", async () => {
    mocks.leerArchivoIntervenciones.mockRejectedValue(new Error("archivo roto"));

    render(<BotonImportarExcel />);
    seleccionarArchivo();

    await waitFor(() => expect(alertSpy).toHaveBeenCalled());
    expect(String(alertSpy.mock.calls[0][0])).toContain("Error al importar: archivo roto");
  });
});
