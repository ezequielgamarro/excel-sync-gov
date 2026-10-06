/**
 * Hook que conecta los filtros globales con la consulta real de la hoja
 * «CONSULTAS» (campos: Resultado, Causas Penales, Jefatura Regional, Turno).
 *
 * Devuelve:
 * - `loading`: petición en curso (la UI muestra skeletons).
 * - `error`: mensaje legible si la consulta falla (la UI muestra un aviso).
 * - `aggregation`: agregación real o `null` (sin ella la UI muestra estado vacío,
 *   NUNCA datos de demostración).
 */

import { useEffect, useState } from "react";
import type { ActiveFilters } from "../components/charts/filters";
import { fetchConsultas } from "../data/api";
import type { ConsultaAggregation } from "../types";

export interface UseConsultasResult {
  aggregation: ConsultaAggregation | null;
  loading: boolean;
  error: string | null;
}

export function useConsultas(filters: ActiveFilters, enabled = true): UseConsultasResult {
  const [aggregation, setAggregation] = useState<ConsultaAggregation | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { turno, unidad, rango } = filters;

  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    setLoading(true);
    setError(null);
    fetchConsultas({
      turno: turno === "TODOS" ? "" : turno,
      unidad: unidad === "TODAS" ? "" : unidad,
      rango,
    })
      .then((data) => {
        if (cancelled) return;
        setAggregation(data);
        setError(null);
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        setAggregation(null);
        setError(cause instanceof Error ? cause.message : "No se pudieron cargar las consultas.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [turno, unidad, rango, enabled]);

  return { aggregation, loading, error };
}
