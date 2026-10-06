/**
 * Hook que conecta el dashboard con la fuente de datos (T50/T51).
 *
 * Une el gestor de conexión (WSS + cold start + polling) con el reducer
 * idempotente, valida defensivamente cada mensaje y mantiene el reloj de
 * frescura (> 120 s → `DATOS DESACTUALIZADOS`, RF-05.h).
 */

import { useEffect, useMemo, useReducer, useRef, useState } from "react";
import { DashboardConnection } from "../data/connection";
import {
  computeStale,
  dashboardReducer,
  initialState,
  type DashboardState,
} from "../state/dashboardReducer";
import { validateSnapshotMessage } from "../lib/validate";

export interface UseDashboardResult {
  state: DashboardState;
  stale: boolean;
  now: number;
  /** Marca (ms) de la última sincronización real (snapshot o heartbeat WSS). */
  lastSyncAt: number;
}

export function useDashboard(enabled: boolean, roomId?: string): UseDashboardResult {
  const [state, dispatch] = useReducer(dashboardReducer, initialState);
  const connectionRef = useRef<DashboardConnection | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [lastSyncAt, setLastSyncAt] = useState(() => Date.now());
  const stateRef = useRef(state);
  stateRef.current = state;

  useEffect(() => {
    if (!enabled) return;
    const connection = new DashboardConnection(
      {
        onSnapshot(raw, coldStart) {
          const result = validateSnapshotMessage(raw);
          if (!result.ok) {
            if (result.reason === "schema_unsupported") {
              dispatch({ type: "schemaError", detail: result.detail });
            } else {
              dispatch({ type: "invalidData", detail: result.detail });
            }
            return;
          }
          dispatch(
            coldStart
              ? { type: "coldStartApplied", message: result.message }
              : {
                  type: "applySnapshot",
                  message: result.message,
                  warnings: result.warnings,
                },
          );
          setLastSyncAt(Date.now());
        },
        onPhase(phase, attempt, degraded) {
          dispatch({ type: "setPhase", phase, attempt });
          dispatch({ type: "setDegraded", degraded });
        },
        onDenied() {
          dispatch({ type: "denied" });
        },
        onHeartbeat() {
          // El servidor confirma que la sesión sigue viva/sincronizada.
          setLastSyncAt(Date.now());
        },
      },
      roomId,
    );
    connectionRef.current = connection;
    connection.start();
    return () => {
      connection.stop();
      connectionRef.current = null;
    };
  }, [enabled, roomId]);

  // Atiende la señal de cold start del reducer por hueco `Δseq > 50`.
  useEffect(() => {
    if (!state.needsColdStart) return;
    const connection = connectionRef.current;
    dispatch({ type: "coldStartRequested" });
    void connection?.requestColdStart();
  }, [state.needsColdStart]);

  // Reloj de frescura (1 s) para el banner y el "hace Xs".
  useEffect(() => {
    if (!enabled) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, [enabled]);

  const stale = useMemo(
    () => computeStale(new Date(lastSyncAt).toISOString(), now),
    [lastSyncAt, now],
  );

  useEffect(() => {
    if (state.stale !== stale) dispatch({ type: "setStale", stale });
  }, [stale, state.stale]);

  return { state, stale, now, lastSyncAt };
}
