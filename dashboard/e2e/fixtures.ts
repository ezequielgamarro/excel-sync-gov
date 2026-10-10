/**
 * Helpers E2E (T67): respuestas REST simuladas del dashboard y un WebSocket
 * falso controlable (histórico). El dashboard es 100% Supabase, por lo que estos
 * mocks cubren solo lo que la SPA consume directamente.
 */

import type { Page } from "@playwright/test";

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
  estadisticas?: Record<string, unknown>;
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

/** Prepara las respuestas REST simuladas del dashboard. */
export async function mockDashboard(page: Page, options: MockOptions = {}): Promise<void> {
  const estadisticas = options.estadisticas ?? makeEstadisticas();

  await page.route("**/api/estadisticas**", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(estadisticas) }),
  );
  await page.route("**/dashboard/consultas**", (route) =>
    route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "sin datos" }) }),
  );
}
