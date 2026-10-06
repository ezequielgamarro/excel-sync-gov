/**
 * Reducer idempotente del estado del dashboard (T51, RNF-11).
 *
 * Reglas de aplicación (RNF-11.b/c/e/f):
 *  - Solo se aplica `seq > lastSeq`.
 *  - Un `event_id` ya aplicado se descarta (idempotencia de red).
 *  - Un salto `Δseq > 50` NO se aplica: solicita un cold start para rellenar.
 *  - La aplicación es **atómica por evento**: el snapshot entero (los 7
 *    visuales) se reemplaza en un único commit de estado React.
 */

import type { SnapshotMessage } from "../types";
import { SUPPORTED_SCHEMA_MAJOR, SCHEMA_VERSION } from "../types";

export const MAX_SEQ_GAP = 50;
export const STALE_THRESHOLD_SECONDS = 120;

export type ConnectionPhase = "loading" | "live" | "reconnecting" | "degraded" | "offline";

export interface DashboardState {
  snapshot: SnapshotMessage | null;
  lastSeq: number;
  seenEventIds: string[];
  phase: ConnectionPhase;
  attempt: number;
  /** WSS sin éxito > 60 s → polling 10 s (RNF-05.d). */
  degraded: boolean;
  stale: boolean;
  invalidData: boolean;
  schemaError: boolean;
  denied: boolean;
  lastEventTs: string | null;
  lastUpdatedAt: number | null;
  warnings: string[];
  /** Señal de efecto: el hook debe solicitar un cold start y limpiarla. */
  needsColdStart: boolean;
}

export const initialState: DashboardState = {
  snapshot: null,
  lastSeq: 0,
  seenEventIds: [],
  phase: "loading",
  attempt: 0,
  degraded: false,
  stale: false,
  invalidData: false,
  schemaError: false,
  denied: false,
  lastEventTs: null,
  lastUpdatedAt: null,
  warnings: [],
  needsColdStart: false,
};

export type DashboardAction =
  | { type: "applySnapshot"; message: SnapshotMessage; warnings?: string[] }
  | { type: "coldStartApplied"; message: SnapshotMessage }
  | { type: "setPhase"; phase: ConnectionPhase; attempt?: number }
  | { type: "setDegraded"; degraded: boolean }
  | { type: "needsColdStart" }
  | { type: "coldStartRequested" }
  | { type: "invalidData"; detail: string }
  | { type: "schemaError"; detail: string }
  | { type: "denied" }
  | { type: "setStale"; stale: boolean };

const SEEN_EVENT_LIMIT = 200;

function rememberEvent(seen: string[], eventId: string): string[] {
  const next = seen.includes(eventId) ? seen : [...seen, eventId];
  return next.length > SEEN_EVENT_LIMIT ? next.slice(next.length - SEEN_EVENT_LIMIT) : next;
}

export function dashboardReducer(state: DashboardState, action: DashboardAction): DashboardState {
  switch (action.type) {
    case "applySnapshot": {
      const { message } = action;
      // Idempotencia por event_id (RNF-11.e).
      if (state.seenEventIds.includes(message.event_id)) return state;
      // Monotonía por seq (RNF-11.b): tardíos/duplicados se descartan.
      if (message.seq <= state.lastSeq) {
        return { ...state, seenEventIds: rememberEvent(state.seenEventIds, message.event_id) };
      }
      // Hueco grande: no se aplica; se pide cold start (RNF-11.c).
      if (state.lastSeq > 0 && message.seq - state.lastSeq > MAX_SEQ_GAP) {
        return { ...state, needsColdStart: true };
      }
      return {
        ...state,
        snapshot: message,
        lastSeq: message.seq,
        seenEventIds: rememberEvent(state.seenEventIds, message.event_id),
        lastEventTs: message.payload.freshness.last_event_ts || message.ts,
        lastUpdatedAt: Date.now(),
        invalidData: false,
        warnings: action.warnings ?? [],
        needsColdStart: false,
      };
    }

    case "coldStartApplied": {
      const { message } = action;
      return {
        ...state,
        snapshot: message,
        lastSeq: message.seq,
        seenEventIds: rememberEvent(state.seenEventIds, message.event_id),
        lastEventTs: message.payload.freshness.last_event_ts || message.ts,
        lastUpdatedAt: Date.now(),
        invalidData: false,
        needsColdStart: false,
      };
    }

    case "setPhase":
      return {
        ...state,
        phase: action.phase,
        attempt: action.attempt ?? state.attempt,
      };

    case "setDegraded":
      return { ...state, degraded: action.degraded };

    case "needsColdStart":
      return { ...state, needsColdStart: true };

    case "coldStartRequested":
      return { ...state, needsColdStart: false };

    case "invalidData":
      return { ...state, invalidData: true };

    case "schemaError":
      return { ...state, schemaError: true };

    case "denied":
      return { ...state, denied: true, phase: "offline" };

    case "setStale":
      return { ...state, stale: action.stale };

    default:
      return state;
  }
}

/** Frescura por `last_event_ts` con tolerancia de deriva (RF-05.h, §13). */
export function computeStale(
  lastEventTs: string | null,
  now: number,
  thresholdSeconds = STALE_THRESHOLD_SECONDS,
): boolean {
  if (!lastEventTs) return false;
  const ts = new Date(lastEventTs).getTime();
  if (Number.isNaN(ts)) return false;
  return (now - ts) / 1000 > thresholdSeconds;
}

export function isSchemaVersionSupported(version: string): boolean {
  const major = Number.parseInt(version.split(".")[0] ?? "", 10);
  return Number.isFinite(major) && major <= SUPPORTED_SCHEMA_MAJOR;
}

export { SCHEMA_VERSION };
