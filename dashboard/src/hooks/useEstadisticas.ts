/**
 * Hook de datos de la hoja `DASHBOARD_WEB`.
 *
 * Carga `GET /api/estadisticas` al montar y expone
 * `{ fase, datos, error, refetch }`, siguiendo el patrón de `useHospitales`.
 * NO existe respaldo con datos de demostración: si la petición falla (red, HTTP
 * o `estado: "error"` en el cuerpo) la fase es `"error"` y `datos` queda `null`.
 *
 * La sección es REACTIVA: un `setInterval` de 60 s vuelve a pedir las
 * estadísticas (pausado con la pestaña oculta) para que la UI refleje la
 * planilla sin botón «Actualizar». `refetch` se conserva para «Reintentar».
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchEstadisticas } from "../data/api";
import type { EstadisticasRespuesta } from "../types";

export type FaseEstadisticas = "cargando" | "listo" | "error";

export interface UseEstadisticasResult {
  fase: FaseEstadisticas;
  datos: EstadisticasRespuesta | null;
  error: string | null;
  /** Fuerza una recarga inmediata (botón «Reintentar» del estado de error). */
  refetch: () => void;
}

/** Cadencia del polling reactivo (ms). */
export const ESTADISTICAS_POLL_MS = 60_000;

export function useEstadisticas(rango?: string): UseEstadisticasResult {
  const [datos, setDatos] = useState<EstadisticasRespuesta | null>(null);
  const [fase, setFase] = useState<FaseEstadisticas>("cargando");
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  // Ref para decidir si corresponde el esqueleto (sólo la primera carga) sin
  // reiniciar la fase en cada pulso del polling.
  const datosRef = useRef<EstadisticasRespuesta | null>(null);

  const refetch = useCallback(() => setReloadKey((key) => key + 1), []);

  useEffect(() => {
    let cancelled = false;
    let inFlight = false;

    const load = async (): Promise<void> => {
      if (cancelled || inFlight) return;
      // La pestaña oculta no dispara nuevas peticiones (ahorro + foco).
      if (typeof document !== "undefined" && document.hidden) return;
      inFlight = true;
      // Sólo bloquea con skeleton la primera carga; el refresco es silencioso.
      if (datosRef.current === null) setFase("cargando");
      setError(null);

      try {
        const payload = await fetchEstadisticas(rango);
        if (cancelled) return;
        // El endpoint puede responder 200 con `estado: "error"` en el cuerpo.
        if (payload.estado === "error") {
          if (datosRef.current === null) {
            setDatos(null);
            setError(
              payload.detalle?.trim() || "El servidor informó un error al leer la planilla.",
            );
            setFase("error");
          }
          return;
        }
        datosRef.current = payload;
        setDatos(payload);
        setFase("listo");
      } catch (cause: unknown) {
        if (cancelled) return;
        // Con datos previos se conserva la última lectura real (nunca demo).
        if (datosRef.current === null) {
          const message = cause instanceof Error ? cause.message : "Error desconocido";
          setDatos(null);
          setError(message || "No se pudieron cargar las estadísticas.");
          setFase("error");
        }
      } finally {
        inFlight = false;
      }
    };

    void load();
    const timer = window.setInterval(() => {
      void load();
    }, ESTADISTICAS_POLL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, [reloadKey, rango]);

  return { fase, datos, error, refetch };
}
