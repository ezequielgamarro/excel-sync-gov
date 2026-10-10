/**
 * Hook de estado del dashboard (migración a Supabase).
 *
 * La API REST de Supabase no mantiene un socket abierto: el panel se considera
 * siempre "EN VIVO". El hook ya no abre red ni WebSockets; solo expone un
 * estado estático y el reloj de la cabecera.
 */

import { useEffect, useState } from "react";
import { initialState, type DashboardState } from "../state/dashboardReducer";

export interface UseDashboardResult {
  state: DashboardState;
  stale: boolean;
  now: number;
  /** Marca (ms) de la última sincronización real. */
  lastSyncAt: number;
}

export function useDashboard(enabled: boolean): UseDashboardResult {
  const [state] = useState<DashboardState>(() => ({ ...initialState, phase: "live" }));
  const [now, setNow] = useState(() => Date.now());
  const [lastSyncAt] = useState(() => Date.now());

  // Reloj de frescura (1 s) para el banner y el "hace Xs".
  useEffect(() => {
    if (!enabled) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [enabled]);

  return { state, stale: false, now, lastSyncAt };
}
