// T69 — Carga REST del cold start / histórico (RNF-04.c/f; CA-02.1).
// Sostiene ≥100 req/s por réplica con p95 ≤800 ms en `GET /dashboard/snapshot`.
//
//   k6 run -e K6_API_URL=https://api.example.gob/api/v1 -e K6_ACCESS_TOKEN=... \
//          -e K6_ROOM_ID=sala-central k6/dashboard-rest.js

import http from "k6/http";
import { check } from "k6";
import { config } from "./lib/signing.js";

const roomId = __ENV.K6_ROOM_ID || "sala-central";

export const options = {
  scenarios: {
    rest: {
      executor: "constant-arrival-rate",
      rate: 100, // ≥100 req/s por réplica (RNF-04.f)
      timeUnit: "1s",
      duration: "1m",
      preAllocatedVUs: 50,
      maxVUs: 200,
    },
  },
  thresholds: {
    http_req_duration: ["p(95)<800", "p(99)<1500"], // cold start p95 ≤800 ms
    http_req_failed: ["rate<0.01"],
    http_reqs: ["rate>=100"],
  },
};

export default function () {
  const response = http.get(
    `${config.apiUrl}/dashboard/snapshot?room_id=${encodeURIComponent(roomId)}`,
    {
      headers: {
        Accept: "application/json",
        Authorization: `Bearer ${config.accessToken}`,
      },
      tags: { endpoint: "snapshot" },
    },
  );
  check(response, {
    "200 OK": (r) => r.status === 200,
    "4 KPIs": (r) => {
      try {
        const body = r.json();
        return body && body.payload && body.payload.kpis && Object.keys(body.payload.kpis).length === 4;
      } catch (_error) {
        return false;
      }
    },
  });
}
