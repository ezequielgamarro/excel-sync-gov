/**
 * Módulo «Carga de Datos»: formulario táctico para registrar una consulta del
 * NUEVO formato. Envía el cuerpo completo a Supabase
 * (`intervenciones_diarias`).
 *
 * Reutiliza `FormularioIntervencion` (mismos campos) y añade el estado de
 * guardado: aviso de éxito «Reporte Guardado», error visible y reseteo del
 * formulario tras cada alta.
 */

import { useEffect, useState } from "react";
import { crearIntervencion, type IntervencionCreate } from "../../data/api";
import { mensajeDeError, registrarEvento } from "../../lib/auditoria";
import {
  FORM_INICIAL,
  FormularioIntervencion,
  type FormValuesIntervencion,
} from "./FormularioIntervencion";

export function FormularioCarga(): JSX.Element {
  const [valoresIniciales, setValoresIniciales] = useState<FormValuesIntervencion>({
    ...FORM_INICIAL,
  });
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [guardado, setGuardado] = useState(false);

  // Auto-oculta el aviso de éxito a los pocos segundos.
  useEffect(() => {
    if (!guardado) return;
    const id = window.setTimeout(() => setGuardado(false), 4000);
    return () => window.clearTimeout(id);
  }, [guardado]);

  const handleSubmit = async (payload: IntervencionCreate): Promise<void> => {
    setGuardado(false);
    setError(null);
    setEnviando(true);
    try {
      await crearIntervencion(payload);
      setValoresIniciales({ ...FORM_INICIAL });
      setGuardado(true);
    } catch (err) {
      console.error("Error Supabase:", err);
      void registrarEvento("error_registro", {
        exito: false,
        entidad: "intervenciones_diarias",
        detalle: { contexto: "crear", mensaje: mensajeDeError(err) },
      });
      const message =
        err instanceof Error ? err.message : "Error desconocido al guardar el reporte.";
      alert("Error al guardar: " + message);
      setError(message);
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="font-display text-xl font-semibold uppercase tracking-wide text-ink">
          Carga de Datos
        </h2>
        <p className="text-sm text-muted">
          Registro táctico de una consulta con el nuevo formato de datos.
        </p>
      </div>

      {guardado ? (
        <p
          role="status"
          aria-live="polite"
          className="rounded-[12px] border border-pos/50 bg-pos/10 px-4 py-3 text-sm font-semibold text-pos"
        >
          ✅ Reporte Guardado
        </p>
      ) : null}

      {error ? (
        <p
          role="alert"
          className="rounded-[12px] border border-neg/50 bg-neg/10 px-4 py-3 text-sm font-semibold text-neg"
        >
          {error}
        </p>
      ) : null}

      <FormularioIntervencion
        valoresIniciales={valoresIniciales}
        onSubmit={handleSubmit}
        enviando={enviando}
      />
    </div>
  );
}
