/**
 * `BotonExportarExcel` — botón reutilizable que descarga el reporte filtrado.
 * Verifica el estado de carga («Generando...» + deshabilitado), el disparo del
 * enlace de descarga y el aviso de error.
 */

import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { FiltersProvider } from "../../state/FiltersContext";

const descargarReportePolicial = vi.hoisted(() => vi.fn());
vi.mock("../../data/api", () => ({ descargarReportePolicial }));

import { BotonExportarExcel } from "./BotonExportarExcel";

function renderBoton(): void {
  render(
    <FiltersProvider>
      <BotonExportarExcel />
    </FiltersProvider>,
  );
}

describe("BotonExportarExcel", () => {
  let createObjectURL: ReturnType<typeof vi.fn>;
  let revokeObjectURL: ReturnType<typeof vi.fn>;
  let clickSpy: ReturnType<typeof vi.spyOn>;
  let alertSpy: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    descargarReportePolicial.mockReset();
    createObjectURL = vi.fn(() => "blob:mock");
    revokeObjectURL = vi.fn();
    Object.defineProperty(URL, "createObjectURL", {
      value: createObjectURL,
      writable: true,
      configurable: true,
    });
    Object.defineProperty(URL, "revokeObjectURL", {
      value: revokeObjectURL,
      writable: true,
      configurable: true,
    });
    clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    alertSpy = vi.fn();
    vi.stubGlobal("alert", alertSpy);
  });

  afterEach(() => {
    clickSpy.mockRestore();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("se deshabilita con «Generando...» mientras descarga y dispara el enlace", async () => {
    let resolver: (blob: Blob) => void = () => {};
    descargarReportePolicial.mockImplementation(
      () =>
        new Promise<Blob>((resolve) => {
          resolver = resolve;
        }),
    );

    renderBoton();
    const boton = screen.getByTestId("boton-exportar-excel");
    expect(boton).toHaveTextContent("Exportar a Excel");
    expect(boton).not.toBeDisabled();

    fireEvent.click(boton);

    // Estado de carga inmediato y filtros activos por defecto.
    expect(boton).toBeDisabled();
    expect(boton).toHaveTextContent("Generando...");
    expect(descargarReportePolicial).toHaveBeenCalledWith({ unidad: "TODAS", rango: "30d" });

    resolver(new Blob(["x"]));

    await waitFor(() => expect(boton).not.toBeDisabled());
    expect(boton).toHaveTextContent("Exportar a Excel");
    expect(clickSpy).toHaveBeenCalledTimes(1);
    expect(createObjectURL).toHaveBeenCalledTimes(1);
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:mock");
  });

  it("avisa por window.alert si la descarga falla", async () => {
    descargarReportePolicial.mockRejectedValue(new Error("sin permiso"));
    renderBoton();

    fireEvent.click(screen.getByTestId("boton-exportar-excel"));

    await waitFor(() => expect(alertSpy).toHaveBeenCalled());
    expect(String(alertSpy.mock.calls[0][0])).toContain("sin permiso");
  });
});
