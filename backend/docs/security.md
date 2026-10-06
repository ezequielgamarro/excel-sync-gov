# Seguridad transversal del backend (F2 — T16–T21)

Documenta las decisiones de seguridad base del backend FastAPI, trazables a la
spec `SPEC-001` (`specs/001_dashboard_monitoreo/spec.md`) y al contrato
(`contracts/openapi.yaml`).

## 1. TLS y HSTS (RNF-01, OD-09)

- **Solo TLS 1.3** (OD-09/RNF-01.a): TLS 1.2 queda **deshabilitado**, sin
  ventana de compatibilidad. El TLS se **termina en el edge**
  (Cloudflare/WAF), que se configura **"TLS 1.3 only"**; cuando el backend
  sirve TLS directamente (`py -m app.core.tls`), `app/core/tls.py` construye
  un `ssl.SSLContext` con `minimum_version = maximum_version = TLSv1_3`. No
  existe ninguna rama que acepte TLS 1.2/1.1.
- Si `FORCE_TLS=true`, se redirige `http → https` con `301` (RNF-01.c). El
  *loopback* nunca se redirige para permitir desarrollo local sin TLS.
- **HSTS** en todas las respuestas (HTML y API):
  `Strict-Transport-Security: max-age=31536000; includeSubDomains; preload`
  (RNF-01.b). Configurable vía `HSTS_MAX_AGE`, `HSTS_INCLUDE_SUBDOMAINS`,
  `HSTS_PRELOAD`; los valores por defecto son los del requisito.

## 2. Cabeceras de hardening (AM-06/AM-10/AM-11/AM-12)

Inyectadas por `SecurityHeadersMiddleware` en **todas** las respuestas:

| Cabecera | Valor | Objetivo |
|----------|-------|----------|
| `Strict-Transport-Security` | `max-age=31536000; includeSubDomains; preload` | HSTS (RNF-01.b) |
| `X-Frame-Options` | `DENY` | Anti-clickjacking (AM-11) |
| `Content-Security-Policy` | `default-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'` | Anti-framing y directivas base (AM-11) |
| `X-Content-Type-Options` | `nosniff` | Anti-MIME sniffing |
| `Referrer-Policy` | `no-referrer` | No filtrar URL en Referer |
| `Cache-Control` | `no-store, private` | Sin caché de datos (AM-10) |
| `Pragma` | `no-cache` | Compatibilidad con cachés intermedias |

La CSP **estricta** de la SPA (`default-src 'self'` sin `unsafe-inline`,
`connect-src` limitado, etc., spec §2.2.5) la sirve **Cloudflare Pages**, no
este backend (la API es otro origen).

## 3. CORS (spec §2.2.2, AM-01/AM-12)

- **Allowlist exacta** de orígenes en `CORS_ALLOW_ORIGINS` (separados por coma).
  Con la lista vacía (por defecto), **no** se permite ningún origen (deny-all).
- `Access-Control-Allow-Credentials` se habilita **solo** cuando la allowlist
  no está vacía (`Settings.cors_effective_allow_credentials`); nunca se combina
  con comodín.
- `Vary: Origin` se garantiza en todas las respuestas con CORS activo mediante
  `CORSVaryMiddleware` (normaliza el valor a un único `Origin`), además del que
  emite `CORSMiddleware` para orígenes permitidos.
- Cabeceras permitidas: `Authorization`, `Content-Type`, `Accept`,
  `X-Correlation-Id`.

## 4. Red interna para `/metrics` y `/health/ready` (RNF-07.c)

`/metrics` y `/health/ready` solo responden desde la **red interna**. La IP del
cliente se valida contra `INTERNAL_NETWORKS` (CIDRs separados por coma). Por
defecto: loopback + RFC1918 (`10/8`, `172.16/12`, `192.168/16`) + `::1`.

`X-Forwarded-For` solo se honra si la IP del proxy está en `TRUSTED_PROXIES`
(vacío por defecto → se usa la IP directa del socket, sin confiar en XFF para
evitar *spoofing*). `/health/live` es público (liveness del proceso).

## 5. Rate limiting (RNF-12, §10.6)

| Bucket | Ruta | Límite (por defecto) | Clave |
|--------|------|----------------------|-------|
| Webhook (origen) | `/api/v1/ingest/*` | 200 req/min, ráfaga 20 | `X-Webhook-Id` |
| Operador | resto de `/api/*` | 120 req/min | `sub` (`X-User-Sub`) |
| Admin | `/api/v1/admin/*` | 50 req/min | `sub` (`X-User-Sub`) |

- Configurable por entorno: `RATE_LIMIT_WEBHOOK_PER_MINUTE`,
  `RATE_LIMIT_WEBHOOK_BURST`, `RATE_LIMIT_OPERATOR_PER_MINUTE`, etc.
- **Base distribuida**: Redis (token bucket con script Lua atómico).
- **Fallback a memoria** por proceso si Redis no está disponible (o
  `RATE_LIMIT_USE_REDIS=false`). **Limitación**: no es distribuido; con varias
  réplicas el límite efectivo se multiplica por el número de réplicas. Se
  reintenta Redis cada 30 s.
- Exceder el límite → `429` con `Retry-After` y cuerpo de error uniforme.
- `/health/*`, `/metrics` y `/schema/*` no se limitan.

## 6. Errores uniformes (§10, §10.5)

Todo error devuelve:

```json
{ "error": { "code": "CAPACIDAD_DENEGADA", "message": "…", "correlation_id": "tr-…" } }
```

`code` es estable y programático; `message` es legible y **sin PII**;
`correlation_id` enlaza con la traza. Handlers registrados para
400/401/403/404/409/413/422/429/500/503 y para los errores de validación de
FastAPI/Starlette. Lanzar errores de negocio con `raise_http_error(code,
message)`.

## 7. Logging sin PII (RNF-07.b, RNF-08.c, RNF-13.b)

Véase también el docstring de `app/core/logging.py`. Reglas:

- Logs **JSON a stdout**, una línea por registro, con `correlation_id`.
- **Prohibido** en logs: nombres de personas, matrículas, armas individuales,
  celdas sensibles del Excel, payloads descifrados, tokens, claves o secretos.
- Los identificadores se **hashean** (`hash_identifier`) o **truncan**
  (`truncate`); nunca en claro.
- Los logs de aplicación son **efímeros** (14–30 días); la auditoría
  append-only (60 meses) es un canal separado (RNF-08.f).
- El formatter solo serializa un conjunto *allowlist* de campos `extra` (nunca
  datos arbitrarios del llamador).
