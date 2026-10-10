/**
 * Botón «Exportar a Excel» reutilizable.
 *
 * Lee los filtros globales (`useFilters`) y descarga el `.xlsx` filtrado
 * generado en el navegador desde Supabase mediante `descargarReportePolicial`.
 * Mientras la petición está en curso el botón se deshabilita y muestra
 * «Generando...». Ante un error avisa por `window.alert` sin romper la vista.
 */

import { useState } from "react";
import { Download } from "lucide-react";
import { descargarReportePolicial } from "../../data/api";
import { useFilters } from "../../state/FiltersContext";
import { mensajeDeError, registrarEvento } from "../../lib/auditoria";

export interface BotonExportarExcelProps {
  /** Clases extra para alinear/espaciar según el contenedor. */
  className?: string;
}

const BOTON_CLASS =
  "touch-target inline-flex items-center gap-2 rounded-[10px] border border-border bg-surface2 px-4 py-2 text-sm font-semibold text-accent transition-colors hover:border-accent hover:bg-accent/10 disabled:cursor-not-allowed disabled:opacity-50";

export function BotonExportarExcel({ className = "" }: BotonExportarExcelProps): JSX.Element {
  const { filters } = useFilters();
  const [isLoading, setIsLoading] = useState(false);

  const handleClick = async (): Promise<void> => {
    if (isLoading) return;
    setIsLoading(true);
    try {
      const blob = await descargarReportePolicial({
        unidad: String(filters.unidad),
        rango: filters.rango,
      });
      const url = URL.createObjectURL(blob);
      const enlace = document.createElement("a");
      enlace.href = url;
      enlace.download = "reporte_policial.xlsx";
      enlace.rel = "noopener";
      document.body.appendChild(enlace);
      enlace.click();
      enlace.remove();
      URL.revokeObjectURL(url);
      void registrarEvento("exportar_excel", {
        detalle: { unidad: String(filters.unidad), rango: String(filters.rango) },
      });
    } catch (cause: unknown) {
      const message = cause instanceof Error ? cause.message : "Error desconocido";
      void registrarEvento("exportar_excel", { exito: false, detalle: { mensaje: mensajeDeError(cause) } });
      window.alert(`No se pudo exportar a Excel: ${message}`);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <button
      type="button"
      data-testid="boton-exportar-excel"
      onClick={() => void handleClick()}
      disabled={isLoading}
      className={`${BOTON_CLASS} ${className}`.trim()}
    >
      <Download size={16} aria-hidden="true" />
      {isLoading ? "Generando..." : "Exportar a Excel"}
    </button>
  );
}
