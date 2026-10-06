import { describe, expect, it } from "vitest";
import {
  computeStale,
  dashboardReducer,
  initialState,
  type DashboardState,
} from "./dashboardReducer";
import { validateSnapshotMessage } from "../lib/validate";
import { makeSnapshot } from "../test/fixtures";
import type { SnapshotMessage } from "../types";

function message(seq: number, eventId: string): SnapshotMessage {
  const result = validateSnapshotMessage(makeSnapshot({ seq, event_id: eventId }));
  if (!result.ok) throw new Error("fixture inválida");
  return result.message;
}

function apply(state: DashboardState, seq: number, eventId: string): DashboardState {
  return dashboardReducer(state, { type: "applySnapshot", message: message(seq, eventId) });
}

describe("reducer idempotente (T51, RNF-11)", () => {
  it("aplica una instantánea mayor y actualiza lastSeq", () => {
    const next = apply(initialState, 10, "evt-1");
    expect(next.lastSeq).toBe(10);
    expect(next.snapshot?.event_id).toBe("evt-1");
  });

  it("descarta seq ≤ lastSeq (tardío/duplicado de red)", () => {
    const first = apply(initialState, 10, "evt-1");
    const second = apply(first, 10, "evt-2");
    expect(second.snapshot).toBe(first.snapshot);
    expect(second.lastSeq).toBe(10);
    const older = apply(first, 7, "evt-3");
    expect(older.snapshot).toBe(first.snapshot);
  });

  it("descarta un event_id ya aplicado aunque el seq avance", () => {
    const first = apply(initialState, 10, "evt-1");
    const second = apply(first, 11, "evt-1");
    expect(second.snapshot).toBe(first.snapshot);
    expect(second.lastSeq).toBe(10);
  });

  it("ante Δseq > 50 no aplica y solicita cold start", () => {
    const first = apply(initialState, 10, "evt-1");
    const gap = apply(first, 70, "evt-2");
    expect(gap.needsColdStart).toBe(true);
    expect(gap.snapshot).toBe(first.snapshot);
    expect(gap.lastSeq).toBe(10);
  });

  it("aplica secuencias contiguas (Δseq ≤ 50)", () => {
    const first = apply(initialState, 10, "evt-1");
    const next = apply(first, 30, "evt-2");
    expect(next.snapshot?.event_id).toBe("evt-2");
    expect(next.lastSeq).toBe(30);
  });

  it("cold start reemplaza el estado y limpia la señal", () => {
    const first = apply(initialState, 10, "evt-1");
    const cold = dashboardReducer(first, {
      type: "coldStartApplied",
      message: message(200, "evt-cold"),
    });
    expect(cold.lastSeq).toBe(200);
    expect(cold.needsColdStart).toBe(false);
  });

  it("calcula frescura con umbral de 120 s", () => {
    const now = Date.parse("2026-10-03T14:24:05.412Z");
    expect(computeStale("2026-10-03T14:22:05.412Z", now)).toBe(false);
    expect(computeStale("2026-10-03T14:20:05.412Z", now)).toBe(true);
    expect(computeStale(null, now)).toBe(false);
  });
});
