// T69 — Fan-out WSS y concurrencia (RNF-04.d/f, RNF-12.d; CA-01.5).
// Abre ≥50 conexiones WSS por sala y mide la latencia de fan-out
// (recepción − `ts` del mensaje, reloj del backend) con p95 ≤100 ms.
//
//   k6 run -e K6_API_URL=... -e K6_WS_URL=wss://.../ws/dashboard \
//          -e K6_ACCESS_TOKEN=... k6/ws-fanout.js

import http from "k6/http";
import ws from "k6/ws";
import { Trend, Counter } from "k6/metrics";
import { check } from "k6";
import {
  config,
  ingestBody,
  randomEventId,
  webhookHeaders,
} from "./lib/signing.js";

const fanout = new Trend("wss_fanout_ms", true);
const snapshots = new Counter("wss_snapshots_received");
const errors = new Counter("wss_errors");

export const options = {
  scenarios: {
    // 50 conexiones concurrentes por sala (RNF-12.d) durante 1 minuto.
    watchers: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        { duration: "5s", target: 50 },
        { duration: "50s", target: 50 },
        { duration: "5s", target: 0 },
      ],
      exec: "watch",
    },
    // Un productor de ediciones para disparar el fan-out.
    producer: {
      executor: "constant-arrival-rate",
      exec: "produce",
      rate: 1,
      timeUnit: "2s",
      duration: "1m",
      preAllocatedVUs: 1,
    },
  },
  thresholds: {
    wss_fanout_ms: ["p(95)<100", "p(99)<200"],
    wss_errors: ["count==0"],
  },
};

function ticket() {
  const response = http.post(`${config.apiUrl}/auth/ws-ticket`, null, {
    headers: { Authorization: `Bearer ${config.accessToken}` },
  });
  return response.json("ticket");
}

export function watch() {
  const tkt = ticket();
  if (!tkt) {
    errors.add(1);
    return;
  }
  const url = `${config.wsUrl}?ticket=${encodeURIComponent(tkt)}`;
  ws.connect(url, {}, (socket) => {
    socket.on("message", (message) => {
      try {
        const data = JSON.parse(message);
        if (data.type === "indicators.snapshot") {
          snapshots.add(1);
          const sentAt = Date.parse(data.ts);
          if (Number.isFinite(sentAt)) fanout.add(Date.now() - sentAt);
        }
      } catch (_error) {
        errors.add(1);
      }
    });
    socket.setTimeout(() => socket.close(), 60_000);
  });
}

export function produce() {
  // Un productor emite una edición firmada para disparar el fan-out.
  const body = ingestBody(randomEventId(), config);
  const signed = webhookHeaders(config, body);
  const response = http.post(config.ingestUrl, body, { headers: signed.headers });
  check(response, { "ingesta 202/200": (r) => r.status === 202 || r.status === 200 });
}
