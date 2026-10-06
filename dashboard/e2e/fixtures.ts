/**
 * Helpers E2E (T67): fixtures del contrato 1.0.0, autenticación nativa simulada
 * y un WebSocket falso controlable (para probar EN VIVO/RECONECTANDO/polling sin
 * depender del backend).
 */

import type { Page } from "@playwright/test";

export const ROOM_ID = "sala-central";

export function makeJwt(capabilities: string[], sub = "e2e"): string {
  const b64 = (value: unknown): string =>
    Buffer.from(JSON.stringify(value)).toString("base64url");
  const header = b64({ alg: "HS256", typ: "JWT" });
  const payload = b64({ sub, capabilities, roles: ["viewer"], aud: "dashboard-api" });
  return `${header}.${payload}.firma-e2e`;
}

export function makeSnapshot(seq: number, overrides: Record<string, unknown> = {}): Record<string, unknown> {
  const base: Record<string, unknown> = {
    schema_version: "1.0.0",
    type: "indicators.snapshot",
    event_id: `evt-${seq}`,
    seq,
    room_id: ROOM_ID,
    ts: "2026-10-03T14:22:05.412Z",
    tz: "America/Argentina/Buenos_Aires",
    tz_offset_minutes: -180,
    data_date: "2026-10-03",
    source: {
      webhook_id: "wh-sifcop-central",
      doc_id: "sifcop-resumen",
      content_sha256: "a".repeat(64),
      sheet_modified_at: "2026-10-03T14:21:58Z",
    },
    payload: {
      kpis: {
        total_consultas_sifcop: kpi(184732, 3120, 1.71),
        personas_capturadas: kpi(4128, 218, 5.57),
        vehiculos_secuestrados: kpi(37, -6, -13.95),
        armas_secuestradas: kpi(12, 2, 20),
      },
      regional: [
        { unidad_id: "capital", label: "Capital", intervenciones: 268, variacion_abs: 22, variacion_pct: 8.93, rank: 1 },
        { unidad_id: "sur", label: "Sur", intervenciones: 142, variacion_abs: -5, variacion_pct: -3.4, rank: 2 },
        { unidad_id: "este", label: "Este", intervenciones: 98, variacion_abs: 7, variacion_pct: 7.74, rank: 3 },
        { unidad_id: "oeste", label: "Oeste", intervenciones: 71, variacion_abs: -3, variacion_pct: -4.05, rank: 4 },
        { unidad_id: "norte", label: "Norte", intervenciones: 34, variacion_abs: 1, variacion_pct: 3.03, rank: 5 },
      ],
      turnos: [
        { turno_id: "MAÑANA", inicio_min: 360, fin_min: 840, label: "MAÑANA (06-14)", intervenciones: 231, variacion_abs: 25, variacion_pct: 12.14, estado: "cerrada" },
        { turno_id: "TARDE", inicio_min: 840, fin_min: 1320, label: "TARDE (14-22)", intervenciones: 318, variacion_abs: 12, variacion_pct: 3.92, estado: "en_curso" },
        { turno_id: "NOCHE", inicio_min: 1320, fin_min: 360, label: "NOCHE (22-06)", intervenciones: 142, variacion_abs: -8, variacion_pct: -5.33, estado: "pendiente" },
      ],
      ranking: {
        top_n: 5,
        dependencias: [
          { puesto: 1, dependencia_id: "com-12", comisaria: "Comisaría 12", intervenciones: 94, variacion_abs: 12, variacion_pct: 14.63, puesto_previo: 2 },
          { puesto: 2, dependencia_id: "com-07", comisaria: "Comisaría 7", intervenciones: 88, variacion_abs: -4, variacion_pct: -4.35, puesto_previo: 1 },
        ],
      },
      freshness: { last_event_ts: "2026-10-03T14:22:05.412Z", stale: false, age_seconds: 0 },
      quality: { partial: false, source_rows: 5, warnings: [] },
    },
    correlation_id: "tr-e2e",
  };
  return deepMerge(base, overrides);
}

function kpi(value: number, deltaAbs: number, deltaPct: number): Record<string, unknown> {
  return {
    label: "KPI",
    value,
    delta_abs: deltaAbs,
    delta_pct: deltaPct,
    direction: deltaAbs > 0 ? "up" : deltaAbs < 0 ? "down" : "flat",
    comparison: "ayer_mismo_tramo",
    baseline_value: value - deltaAbs,
    as_of: "2026-10-03T14:22:05Z",
    has_reference: true,
  };
}

function deepMerge(target: Record<string, unknown>, source: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = { ...target };
  for (const [key, value] of Object.entries(source)) {
    const current = out[key];
    if (
      value &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      current &&
      typeof current === "object" &&
      !Array.isArray(current)
    ) {
      out[key] = deepMerge(current as Record<string, unknown>, value as Record<string, unknown>);
    } else {
      out[key] = value;
    }
  }
  return out;
}

/** Instala un WebSocket falso controlable desde el test (window.__ws*). */
export async function installFakeWebSocket(page: Page, options: { autoOpen?: boolean } = {}): Promise<void> {
  const autoOpen = options.autoOpen ?? true;
  await page.addInitScript(
    ({ autoOpen: open }) => {
      const store = window as unknown as {
        __fakeSockets: Array<Record<string, unknown>>;
        __pushSnapshot: (msg: unknown) => void;
        __dropSocket: (code?: number) => void;
        __pushHello: () => void;
      };
      store.__fakeSockets = [];
      class FakeWebSocket {
        static OPEN = 1;
        static CLOSED = 3;
        static CLOSING = 2;
        static CONNECTING = 0;
        readyState = 1;
        onopen: ((event: unknown) => void) | null = null;
        onmessage: ((event: { data: string }) => void) | null = null;
        onerror: ((event: unknown) => void) | null = null;
        onclose: ((event: { code: number; reason: string }) => void) | null = null;
        sent: string[] = [];
        constructor(public url: string) {
          store.__fakeSockets.push(this as unknown as Record<string, unknown>);
          if (open) {
            setTimeout(() => {
              this.onopen?.({});
              this.onmessage?.({
                data: JSON.stringify({
                  type: "hello",
                  room_id: "sala-central",
                  schema_version: "1.0.0",
                  server_ts: new Date().toISOString(),
                  last_seq: 0,
                  heartbeat_interval_s: 15,
                }),
              });
            }, 0);
          }
        }
        send(data: string): void {
          this.sent.push(data);
        }
        close(code = 1000, reason = ""): void {
          if (this.readyState === 3) return;
          this.readyState = 3;
          this.onclose?.({ code, reason });
        }
      }
      (window as unknown as { WebSocket: unknown }).WebSocket = FakeWebSocket;
      const latest = () => store.__fakeSockets[store.__fakeSockets.length - 1] as unknown as FakeWebSocket | undefined;
      store.__pushSnapshot = (msg: unknown) => {
        latest()?.onmessage?.({ data: JSON.stringify(msg) });
      };
      store.__dropSocket = (code = 1006) => {
        latest()?.close(code, "e2e-drop");
      };
      store.__pushHello = () => {
        latest()?.onmessage?.({
          data: JSON.stringify({ type: "hello", room_id: "sala-central", schema_version: "1.0.0", server_ts: new Date().toISOString(), last_seq: 0, heartbeat_interval_s: 15 }),
        });
      };
    },
    { autoOpen },
  );
}

export interface MockOptions {
  snapshot?: Record<string, unknown>;
  estadisticas?: Record<string, unknown>;
  capabilities?: string[];
  denyTicket?: boolean;
}

/** Respuesta REAL simulada de `GET /api/estadisticas` (totales + gráficos). */
export function makeEstadisticas(): Record<string, unknown> {
  return {
    estado: "exito",
    totales: {
      total_consultas: 365,
      aprehendidos: 10,
      vehiculos_secuestrados: 4,
      armas_secuestradas: 2,
    },
    kpis: {
      total_consultas: 365,
      personas: 10,
      vehiculos: 4,
      armas: 2,
      positivos: 30,
      negativos: 5,
    },
    incidentes_por_fecha: [
      { fecha: "01/10", total: 6 },
      { fecha: "02/10", total: 11 },
    ],
    vehiculosPorRegional: [{ name: "Unidad Regional Sur", value: 4 }],
    armasPorRegional: [{ name: "Unidad Regional Norte", value: 2 }],
    rankingTop5: [{ name: "Comisaría 12", value: 94 }],
    grafico_regionales: [{ name: "Capital", value: 268 }],
    grafico_dependencias: [{ name: "Comisaría 12", value: 94 }],
    alertas_resultados: [{ name: "POSITIVO", value: 30 }],
  };
}

/** Autentica y prepara REST + WSS simulados. */
export async function mockDashboard(page: Page, options: MockOptions = {}): Promise<void> {
  const snapshot = options.snapshot ?? makeSnapshot(100);
  const estadisticas = options.estadisticas ?? makeEstadisticas();
  const capabilities = options.capabilities ?? ["dash.view.live"];
  const token = makeJwt(capabilities);

  await page.addInitScript(() => {
    window.sessionStorage.setItem("dash.auth.refresh", "rt-e2e");
  });

  await page.route("**/api/v1/auth/refresh", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ access_token: token, refresh_token: "rt-e2e", csrf_token: "csrf-e2e", expires_in: 900, capabilities }),
    }),
  );
  await page.route("**/api/v1/auth/logout", (route) => route.fulfill({ status: 200, contentType: "application/json", body: "{}" }));
  await page.route("**/api/v1/dashboard/snapshot**", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(snapshot) }),
  );
  await page.route("**/api/estadisticas**", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(estadisticas) }),
  );
  await page.route("**/dashboard/consultas**", (route) =>
    route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "sin datos" }) }),
  );
  await page.route("**/api/v1/auth/ws-ticket", (route) => {
    if (options.denyTicket) {
      return route.fulfill({
        status: 403,
        contentType: "application/json",
        body: JSON.stringify({ error: { code: "CAPACIDAD_DENEGADA", message: "denegado" } }),
      });
    }
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ticket: "tkt_e2e", expires_in: 60 }),
    });
  });
}
