// T69 — Carga del webhook de ingesta (RNF-04.a, RNF-12.a; CA-01.1/01.2).
// Verifica la latencia del backend (≤350 ms p95) y el rate limit del webhook
// (200 req/min, ráfaga 20) con `429` al excederlo.
//
//   k6 run -e K6_WEBHOOK_ID=... -e K6_WEBHOOK_KEY_ID=... -e K6_WEBHOOK_SECRET=... \
//          -e K6_INGEST_URL=https://api.example.gob/api/v1/ingest/webhook k6/ingest-webhook.js

import http from "k6/http";
import { Counter } from "k6/metrics";
import { check, sleep } from "k6";
import { config, ingestBody, randomEventId, webhookHeaders } from "./lib/signing.js";

const accepted = new Counter("ingest_accepted");
const rateLimited = new Counter("ingest_rate_limited");
const rejectedOther = new Counter("ingest_rejected_other");

export const options = {
  scenarios: {
    // Ritmo operativo (carga media 100–1000 ediciones/día, OD-08).
    steady: {
      executor: "constant-arrival-rate",
      exec: "sendIngest",
      rate: 3,
      timeUnit: "1s",
      duration: "1m",
      preAllocatedVUs: 5,
      maxVUs: 20,
      tags: { scenario: "steady" },
    },
    // Ráfaga para forzar el rate limit (ráfaga 20 → 429).
    burst: {
      executor: "constant-vus",
      exec: "sendIngest",
      vus: 20,
      duration: "10s",
      startTime: "65s",
      tags: { scenario: "burst" },
    },
  },
  thresholds: {
    "http_req_duration{scenario:steady}": ["p(95)<350"],
    "http_req_failed{scenario:steady}": ["rate<0.01"],
    ingest_rate_limited: ["count>0"],
  },
};

export function sendIngest() {
  const body = ingestBody(randomEventId(), config);
  const signed = webhookHeaders(config, body);
  const response = http.post(config.ingestUrl, body, { headers: signed.headers });

  if (response.status === 202) accepted.add(1);
  else if (response.status === 200) accepted.add(1);
  else if (response.status === 429) rateLimited.add(1);
  else rejectedOther.add(1);

  check(response, {
    "status 202/200/429": (r) => [200, 202, 429].includes(r.status),
    "cuerpo JSON": (r) => /duplicate|event_id|error/.test(r.body || ""),
  });
  sleep(0.05);
}
