/**
 * Botón «Importar Datos» reutilizable.
 *
 * Abre un selector de archivos (`.xlsx`/`.xls`/`.csv`), lee las filas con
 * `leerArchivoIntervenciones`, las inserta en Supabase con
 * `importarIntervenciones` y emite `INTERVENCIONES_REFRESH_EVENT` para que el
 * dashboard y el historial se recarguen. Durante la operación el botón se
 * deshabilita y muestra «Importando…». Los errores se avisan por `window.alert`
 * sin romper la vista.
 */

import { useRef, useState } from "react";
import type { ChangeEvent } from "react";
import { Upload } from "lucide-react";
import {
  INTERVENCIONES_REFRESH_EVENT,
  importarIntervenciones,
  leerArchivoIntervenciones,
} from "../../data/importarIntervenciones";
import { mensajeDeError, registrarEvento } from "../../lib/auditoria";

export interface BotonImportarExcelProps {
  /** Clases extra para alinear/espaciar según el contenedor. */
  className?: string;
}

const BOTON_CLASS =
  "touch-target inline-flex items-center gap-2 rounded-[10px] border border-border bg-surface2 px-4 py-2 text-sm font-semibold text-accent transition-colors hover:border-accent hover:bg-accent/10 disabled:cursor-not-allowed disabled:opacity-50";

export function BotonImportarExcel({ className = "" }: BotonImportarExcelProps): JSX.Element {
  const inputRef = useRef<HTMLInputElement>(null);
  const [cargando, setCargando] = useState(false);

  const handleChange = async (event: ChangeEvent<HTMLInputElement>): Promise<void> => {
    const target = event.currentTarget;
    const file = target.files?.[0];
    if (!file) return;

    setCargando(true);
    try {
      const filas = await leerArchivoIntervenciones(file);
      if (filas.length === 0) {
        window.alert("No se encontraron filas válidas para importar.");
        return;
      }
      const n = await importarIntervenciones(filas);
      void registrarEvento("importar_excel", { detalle: { registros: n, archivo: file.name } });
      window.alert(`Se importaron ${n} registros correctamente`);
      window.dispatchEvent(new Event(INTERVENCIONES_REFRESH_EVENT));
    } catch (err) {
      void registrarEvento("importar_excel", {
        exito: false,
        detalle: { archivo: file.name, mensaje: mensajeDeError(err) },
      });
      window.alert("Error al importar: " + (err instanceof Error ? err.message : String(err)));
    } finally {
      target.value = "";
      setCargando(false);
    }
  };

  return (
    <>
      <input
        ref={inputRef}
        type="file"
        accept=".xlsx, .xls, .csv"
        className="hidden"
        data-testid="input-importar-excel"
        onChange={(event) => void handleChange(event)}
      />
      <button
        type="button"
        data-testid="boton-importar-excel"
        onClick={() => inputRef.current?.click()}
        disabled={cargando}
        className={`${BOTON_CLASS} ${className}`.trim()}
      >
        <Upload size={16} aria-hidden="true" />
        {cargando ? "Importando…" : "Importar Datos"}
      </button>
    </>
  );
}
