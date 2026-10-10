# Pruebas de carga k6 (T69)

Verifican los objetivos de rendimiento de la spec (§6 RNF-04, RNF-12):

| Escenario | Objetivo | Archivo |
|-----------|----------|---------|
| Ingesta del webhook | p95 ≤ 350 ms; rate limit 200 req/min → `429` | `ingest-webhook.js` |
| Cold start REST | ≥ 100 req/s por réplica; p95 ≤ 800 ms | `dashboard-rest.js` |
| Fan-out WSS | ≥ 50 conexiones/sala; fan-out p95 ≤ 100 ms | `ws-fanout.js` |

## Variables de entorno

| Variable | Uso |
|----------|-----|
| `K6_INGEST_URL` | `POST /api/v1/ingest/webhook` (origen allowlisted) |
| `K6_API_URL` | Base REST (`/api/v1`) |
| `K6_WS_URL` | `wss://.../api/v1/ws/dashboard` |
| `K6_ACCESS_TOKEN` | JWT de un operador `viewer`/`supervisor` de prueba |
| `K6_WEBHOOK_ID`, `K6_WEBHOOK_KEY_ID`, `K6_WEBHOOK_SECRET` | Credenciales de prueba del webhook (secreto en hex) |
| `K6_ROOM_ID` | Sala a medir (por defecto `sala-central`) |

> Los secretos son de **prueba**, nunca de producción (RNF-13.d). No se versionan.

## Ejecución

```bash
k6 run \
  -e K6_WEBHOOK_ID=... -e K6_WEBHOOK_KEY_ID=... -e K6_WEBHOOK_SECRET=... \
  -e K6_INGEST_URL=https://api.staging.gob/api/v1/ingest/webhook \
  k6/ingest-webhook.js

k6 run -e K6_API_URL=https://api.staging.gob/api/v1 \
  -e K6_ACCESS_TOKEN=... k6/dashboard-rest.js

k6 run -e K6_API_URL=https://api.staging.gob/api/v1 \
  -e K6_WS_URL=wss://api.staging.gob/api/v1/ws/dashboard \
  -e K6_ACCESS_TOKEN=... -e K6_INGEST_URL=https://api.staging.gob/api/v1/ingest/webhook \
  k6/ws-fanout.js
```

Los umbrales (`thresholds`) **fallan** la ejecución si no se cumplen: encadenar en CI de rendimiento (T75). El objetivo E2E de p95 ≤ 1,5 s edición→visual se mide además con las marcas `performance.now()` del navegador (Playwright, T67) y el histograma de observabilidad (RNF-07.f).
