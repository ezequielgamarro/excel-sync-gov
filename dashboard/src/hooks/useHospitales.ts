/**
 * Hook de datos del módulo de ingresos hospitalarios.
 *
 * Carga `GET /api/hospitales/estadisticas` una vez al montar y expone
 * `loading`/`error`/`reload` (+ `retry`) siguiendo el patrón de `useDashboard`
 * y `useConsultas`. `reload()` fuerza una nueva petición (reintento manual).
 */

import { useCallback, useEffect, useState } from "react";
import { fetchHospitalesEstadisticas } from "../data/api";
import type { HospitalesEstadisticas } from "../types";

export interface UseHospitalesResult {
  data: HospitalesEstadisticas | null;
  loading: boolean;
  error: string | null;
  /** Recarga los datos (usado por el botón «Reintentar»). */
  reload: () => void;
}

export function useHospitales(): UseHospitalesResult {
  const [data, setData] = useState<HospitalesEstadisticas | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);

  const reload = useCallback(() => setReloadKey((key) => key + 1), []);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchHospitalesEstadisticas()
      .then((payload) => {
        if (!cancelled) setData(payload);
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        const message = cause instanceof Error ? cause.message : "Error desconocido";
        setError(message || "No se pudieron cargar las estadísticas de hospitales.");
        setData(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [reloadKey]);

  return { data, loading, error, reload };
}
