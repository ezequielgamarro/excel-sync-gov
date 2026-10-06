# TASKS-001 — Desglose de Tareas "Google Sheets-to-Web" + Dashboard de Monitoreo

**Spec:** `spec.md` · **Plan:** `plan.md`
**Convención:** cada tarea es atómica y verificable. `ID` secuencial, `Fase` (F0..F10), `Dep.` = IDs de tareas previas que deben estar completas. Las columnas CA y RF/RNF referencian la spec (§12, §5, §6).

---

## Fase F0 — Contratos y scaffolding

| ID | Título | Descripción | Dep. | CA | RF/RNF |
|----|--------|-------------|------|----|--------|
| T1 | Repositorio monorepo y estructura | Crear estructura `backend/`, `apps-script/`, `dashboard/`, `infra/`, `specs/`, `contracts/` con convenciones de layout, `.editorconfig`, `README` y gitignore. Definir rutas de contratos y versionado. | — | — | — |
| T2 | JSON Schema de mensajes (§7.2–§7.8) | Escribir `contracts/messages/1.0.0.schema.json` con el sobre `indicators.snapshot` completo: `schema_version`, `type`, `event_id`, `seq`, `room_id`, `ts`, `tz`, `data_date`, `payload` (kpis/regional/turnos/ranking/freshness/quality). Incluir ejemplos válidos. CI valida que los ejemplos cumplen el schema. | T1 | — | §7, RNF-15 |
| T3 | Contrato OpenAPI (§10) | Generar `contracts/openapi.yaml` como fuente única de la API: `/ingest/webhook`, `/admin/webhook/secret/rotate`, `/dashboard/snapshot`, `/dashboard/history`, `/dashboard/export.csv`, `/audit/events`, `/auth/login`, `/auth/refresh`, `/auth/logout`, `/auth/ws-ticket`, `/ws/dashboard`, `/health/*`, `/metrics`, `/schema/messages/{version}` y endpoints admin (§10.6). Errores con cuerpo uniforme. | T1 | — | §10 |
| T4 | CI base y secret scanning | Pipeline base (GitHub Actions/equivalente): lint + typecheck Python y Node, y **secret scanning** que bloquea el merge ante secretos plausibles. Matrix de versiones Python/Node. | T1 | — | RNF-13.d |
| T5 | Estándares y versionado semver | Configurar `ruff`/`black` (Python) y ESLint/Prettier (Node), pre-commit hooks, y política de versionado semver de mensajes y artefactos (§7.8). | T1 | — | §7.8 |
| T6 | Plantilla de secretos y doc | Crear `.env.example` con nombres (sin valores) de todos los secretos (§9.5) y documentar su custodia/rotación. Prohibir `.env` versionado. | T1 | — | RNF-13, §9.5 |

---

## Fase F1 — Modelo de datos y PostgreSQL

| ID | Título | Descripción | Dep. | CA | RF/RNF |
|----|--------|-------------|------|----|--------|
| T7 | Migración base + extensiones | Framework de migraciones (Alembic) y habilitar `pgcrypto`, `uuid-ossp` (UUIDv7). Scripts idempotentes up/down. | T1 | — | RNF-02 |
| T8 | Tabla `ingest_event` | Cabecera de cada evento: `event_id` UUIDv7 **UNIQUE**, `doc_id`, `webhook_id`, `content_sha256`, `payload_ciphertext` (AES-256-GCM en reposo), `seq`, `received_at`, `correlation_id`. Retención 90 días (particionado por mes). | T7 | CA-01.1, CA-01.5 | RF-01, RNF-02.a, RNF-11.a |
| T9 | Tabla `snapshot_current` | Último payload aceptado por `doc_id` (1 fila/doc), base del cold start. | T7 | — | §7.9, RNF-06.e |
| T10 | Tablas `agg_hourly` + `agg_daily` | Agregados por hora/día/unidad/turno/KPI; `agg_daily` alimenta baselines "ayer". Retención 60 meses. | T7 | — | §7.9, RNF-02 |
| T11 | Tabla `ranking_snapshot` | Top 5 por día/turno (histórico de ranking) para `puesto_previo`. Retención 60 meses. | T7 | CA-04.5 | §7.9 |
| T12 | Tabla `audit_event` (append-only) | Bitácora con `ts`, `actor`, `action`, `resource`, `result`, `ip` (seudonimizada), `user_agent`, `correlation_id`, `schema_version`. **Sin** UPDATE/DELETE para el rol de servicio. Retención 60 meses. | T7 | CA-01.2, CA-02.10 | RNF-08 |
| T13 | Tablas `webhook_registry` + `webhook_secret` | Registro de webhooks (estado, documento asociado, revocación) y versiones del secreto de webhook (`key_id`, estado, fechas); el material del secreto vive en el secret manager, no en la BD. | T7 | CA-01.2 | RF-01, RNF-02.e, §9 |
| T14 | Tablas de identidad local + seeds | Tablas `app_user` (usuario, hash **Argon2id**, estado, intentos fallidos) y `refresh_token` (rotativo, hash, revocación); mapeo `role_capability` rol→capacidad (configurable en backend, sin IdP externo). Seed de roles (`viewer`,`supervisor`,`auditor`,`platform-admin`) y capacidades (§2.2.3). | T7 | CA-01.8, CA-02.9 | RNF-03, §2.2.3 |
| T15 | Rol `svc_dashboard` + particionado + cifrado | Identidad de servicio de mínimo privilegio: `SELECT` solo vistas/agregados, `INSERT`+`SELECT` en `audit_event`, sin DDL/DELETE. Particionado por mes y cifrado de columna `payload_ciphertext` con `pgcrypto`. | T8, T12 | — | RNF-02, §2.2.4 |

---

## Fase F2 — Backend núcleo y seguridad transversal

| ID | Título | Descripción | Dep. | CA | RF/RNF |
|----|--------|-------------|------|----|--------|
| T16 | App FastAPI + config + health | Esqueleto de la app, configuración desde entorno (secret manager), y endpoints `/health/live` y `/health/ready` (BD+Redis). | T1 | — | RNF-07.c |
| T17 | Logging estructurado sin PII | Logger JSON a stdout con `correlation_id` (middleware `X-Correlation-Id`), **sin PII** (hash/trunc de identificadores; nunca celdas sensibles). | T16 | — | RNF-08.c/f |
| T18 | Seguridad base: TLS/HSTS/headers/CORS | Forzar TLS 1.3 (rechazar 1.2), HSTS `max-age=31536000; includeSubDomains; preload`, `X-Frame-Options: DENY`, `frame-ancestors 'none'`, `no-store` en datos, CORS con allowlist exacta y `Vary: Origin`. | T16 | CA-05.1 | RNF-01, AM-03, AM-11 |
| T19 | Rate limiting base | Middleware de rate limit: webhook 200 req/min (ráfaga 20) por `webhook_id`; operador 120 req/min por `sub`; `429` con `Retry-After`. Base distribuida (Redis). | T16 | CA-01.2 | RNF-12.a/b, AM-07 |
| T20 | Errores uniformes | Cuerpo de error único `{error:{code,message,correlation_id}}` y códigos §10.5 (400/401/403/404/409/413/422/429/500/503). | T16 | CA-01.2 | §10.5 |
| T21 | `/metrics` y healthchecks | Endpoint `/metrics` (Prometheus) solo red interna; métricas de latencia, eventos/s, conexiones WSS, rechazos, payload size, 4xx/5xx. | T16 | — | RNF-07.a/c |

---

## Fase F3 — Ingesta segura

| ID | Título | Descripción | Dep. | CA | RF/RNF |
|----|--------|-------------|------|----|--------|
| T22 | Verificación de firma HMAC-SHA256 + secreto de webhook | Implementar la verificación de `X-Webhook-Signature` sobre la cadena canónica (§9.2), con comparación en tiempo constante y `key_id` vigente; el material del secreto se inyecta desde el secret manager (nunca de la BD). | T2, T13 | CA-01.3 | RF-01.f, RNF-01.f, §9 |
| T23 | Autenticación del webhook (firma HMAC) | Verificar en orden y **antes de deserializar**: formato de cabeceras, `webhook_id` activo/no revocado, `key_id` vigente, firma HMAC-SHA256 válida y timestamp dentro de ±300 s. | T13 | CA-01.2 | RF-01.e, RNF-03.f, AM-04 |
| T24 | Anti-replay | Nonce de 128 bits no visto en ventana (cache 600 s) + timestamp dentro de ±300 s. `409` ante repetición/desalineación. | T23 | CA-01.6 | RF-01.k, RNF-03.f, AM-05 |
| T25 | Validación de esquema/rangos/catálogos | Validar payload contra JSON Schema y catálogos fijos (5 unidades, 3 turnos, 4 KPIs, ranking ≤5); KPI negativo/NaN → `422`; unidad/turno fuera de allowlist → `rejected_*`; payload > 256 KB plano / 64 KB comprimido → `413`. | T2 | CA-03.3 | RF-01.l, RF-03.h, RNF-12.f, AM-07 |
| T26 | `POST /ingest/webhook` + idempotencia | Endpoint completo: verificación de firma → validación → `INSERT` idempotente por `event_id` UNIQUE → UPSERT `snapshot_current` → agregados → `audit_event` (aceptado/rechazado con causa) → redistribución. Responde `202`/`200 duplicate=true`. | T22–T25 | CA-01.1, CA-01.5, CA-01.7 | RF-01, RNF-11.a |
| T27 | Provisión/rotación del secreto de webhook | `POST /admin/webhook/secret/rotate`: genera `webhook_id`+`key_id`+secreto (mostrado **una sola vez**), con solape de 24 h y auditoría de rotación. | T13 | CA-01.2 | §10.1, RNF-03.f |

---

## Fase F4 — Distribución en tiempo real

| ID | Título | Descripción | Dep. | CA | RF/RNF |
|----|--------|-------------|------|----|--------|
| T28 | Redis pub/sub fan-out + `seq` | Publicar eventos aceptados por `room_id`; asignar `seq` monotónico por sala; replicar a N réplicas. | T26 | CA-01.5 | RNF-04.d, RNF-06.c |
| T29 | Ticket WSS + endpoint `/ws/dashboard` | `POST /auth/ws-ticket` (capacidad `dash.view.live`) emite ticket de **un solo uso** (TTL 60 s) que encarna `sub`+capacidades+`room_id`. Apertura WSS valida ticket, envía `hello` con `last_seq` y `heartbeat_interval_s`. Códigos de cierre 4001/4003/4401/4403. | T28, T37 | CA-01.8 | RNF-03.d, §10.3 |
| T30 | Cold start `GET /dashboard/snapshot` | Devuelve snapshot desde `snapshot_current`/agregados (p95 ≤ 800 ms); funciona **sin Redis** (lee PostgreSQL). Capacidad `dash.view.live`; `409` si hay uno más nuevo vía WSS. | T9, T26 | CA-02.1 | RNF-04.c, RNF-06.e |
| T31 | Histórico + export CSV | `GET /dashboard/history` (bucket hour/day, rango ≤90 d supervisor / 60 m auditor) y `GET /dashboard/export.csv` (capacidad `dash.export.csv` auditada, sin step-up; cabecera de auditoría). | T10, T30 | — | §10.2, RNF-03.g, AM-09 |
| T32 | `GET /audit/events` | Consulta de auditoría (capacidad `audit.view`), filtros `from/to/actor/action/event_id`, sin PII. | T12 | CA-02.10 | RNF-08.d |
| T33 | Agregados y variación "vs ayer" | Calcular en backend `delta_abs`/`delta_pct`/`direction`/`baseline_value` con `ayer_mismo_tramo` (y `ayer_mismo_turno` para turnos), cache por `data_date`+`turno_id`. `has_reference=false` cuando no hay baseline. | T10, T11 | CA-02.3, CA-02.4 | RF-02.d, §7.3, RNF-15.b |

---

## Fase F5 — Autenticación nativa JWT y RBAC

| ID | Título | Descripción | Dep. | CA | RF/RNF |
|----|--------|-------------|------|----|--------|
| T34 | Usuario local + hash de contraseña | Entidad `app_user`: `username`, hash **Argon2id** (sal por usuario), estado, intentos fallidos; política de contraseñas y **bloqueo por intentos** con backoff progresivo; auditoría de altas/bajas. | T14 | CA-02.9 | RNF-03.a/i, OD-05 |
| T35 | Emisión y refresh de JWT nativo | Firmar/validar JWT de acceso (15 min) con `JWT_SIGNING_KEY` (rotación con solape); refresh token rotativo con **reuse detection** (reuso revoca la cadena) y revocación en logout; rate limit de login. | T34 | CA-02.9 | RNF-03.b, §10.6 |
| T36 | Endpoints `/auth/login|refresh|logout` + gestión de usuarios locales | `POST /auth/login`, `POST /auth/refresh`, `POST /auth/logout` (nativos) y endpoints de administración de usuarios locales (crear/actualizar/deshabilitar/reset-password/roles) con capacidad `platform.manage_users`, rate limit 50 req/min y auditoría de cambios (`user.created/updated/disabled`, `role.assigned/revoked`). Mantener `POST /auth/ws-ticket`. | T35 | — | §10.6, RNF-08.a |
| T37 | RBAC por capacidad + re-verificación | Middleware de capacidades (deny por defecto) en cada endpoint y en apertura WSS; re-verificación periódica; revocación/cierre de WSS en ≤30 s cuando el usuario pierde rol o se deshabilita. | T14, T35 | CA-01.8, CA-02.9 | RNF-03.c/e/h, AM-01, AM-02 |

---

## Fase F6 — Integración Google Sheets

| ID | Título | Descripción | Dep. | CA | RF/RNF |
|----|--------|-------------|------|----|--------|
| T38 | Apps Script: trigger instalable `onEdit`/`onChange` | Script vinculado al documento; detecta la edición, coalesce ráfagas (750 ms) y descarta no-ops; registra en el log de ejecución. | T1 | CA-01.4 | RF-01.a/b |
| T39 | Apps Script: lectura y normalización de la hoja | Leer rangos con `SpreadsheetApp` en solo lectura; normalizar; validar cabeceras contra allowlist (mapeo 1:1 hojas→series); fallar cerrado con aviso accionable. | T38 | — | RF-01.c, OOS-06, OD-15 |
| T40 | Apps Script: hash de contenido + deduplicación | Calcular `content_sha256` del contenido normalizado; omitir el envío si es idéntico al último exitoso. | T39 | CA-01.4 | RF-01.c, AM-08 |
| T41 | Apps Script: firma HMAC-SHA256 + nonce + timestamp | Construir el cuerpo canónico; firmar con HMAC-SHA256 (secreto en `Script Properties`), nonce de 128 bits y timestamp UTC. | T40 | CA-01.1, CA-01.3 | RF-01.d/f, §9 |
| T42 | Activación/rotación del secreto en `Script Properties` | Configurar `webhook_id`+`key_id`+secreto en `Script Properties`; solape 24 h; **nunca** en el código `.gs` ni versionado. | T27, T41 | CA-01.2 | §9.3/§9.4, RNF-03.f, AM-14 |
| T43 | Apps Script: reintentos con backoff + reconciliación | `UrlFetchApp` con backoff 2/4/8/16/32/60 s y jitter ±20 %; persistir el último hash; el backend reconcilia por polling al recuperarse. | T42 | CA-01.7 | RF-01.i, RNF-06.f |
| T44 | Cliente HTTPS TLS 1.3 + códigos | Envío HTTPS a `api.<dominio-gob>` (allowlist); manejo: 401/403 → alertar/verificar secreto; 409 → regenerar nonce y reintentar una vez; 429 → `Retry-After`; 413/422 → alertar. | T43 | CA-01.6 | RF-01.e/k, RNF-01.a |
| T45 | Reconciliación por polling de respaldo (backend) | Job programado con la API de Google Sheets (service account de solo lectura) que compara `content_sha256` contra `snapshot_current` y emite evento si hubo cambios no notificados por el webhook. | T39, T44 | CA-01.4 | RF-01.a/i, RNF-06.f |
| T46 | Modo degradado + salud del origen | Marcar modo degradado a los >15 min sin webhook; registro y reporte de salud (última recepción, reintentos agotados); sin descartar datos. | T43 | CA-01.7 | RF-01.j |

---

## Fase F7 — Dashboard React

| ID | Título | Descripción | Dep. | CA | RF/RNF |
|----|--------|-------------|------|----|--------|
| T47 | Scaffold + PWA shell | Vite + React 18 + Tailwind + Recharts; PWA con manifest y **service worker solo de shell** (precache app shell; **jamás** cachear API/WSS). | T1 | — | RNF-10.e, AM-10 |
| T48 | Tokens de diseño + retícula | Implementar paleta (§11.2/Anexo B), tipografía Inter, `tabular-nums`, retícula 12 col (gutter 24 px, padding 24 px), responsive 1920/2560/3840, `min-width` 1280 px. | T47 | CA-05.1, CA-05.2 | RF-05.a–e, RNF-10.b/c |
| T49 | Formulario de login + almacenamiento seguro de tokens | Formulario usuario/contraseña contra `/auth/login`; access token en memoria y refresh con almacenamiento seguro, `no-store`, `Clear-Site-Data` en logout; **sin** secretos en el bundle. | T36, T47 | CA-02.9 | RNF-03.a/b, RNF-13.b |
| T50 | Capa de datos (cold start + WSS) | Cold start REST + cliente WSS; reconexión backoff 1→30 s con jitter; heartbeat 15 s (cierre si 45 s sin actividad); degradación a polling 10 s tras 60 s; estados de conexión. | T30, T29, T47 | CA-05.8 | RF-05.g, RNF-05 |
| T51 | Estado idempotente (seq/event_id) | Reducer que aplica solo `seq > lastSeq`, descarta `event_id` duplicado, y ante `Δseq > 50` pide cold start; commit atómico de los 7 visuales. | T50 | CA-02.5, CA-02.6 | RNF-11 |
| T52 | Tarjetas KPI (VIS-01..04) | 4 tarjetas en fila superior (colspan 3), valor 34 px tabular, variación con glifo+signo+% y `vs ayer`, color por dirección, animación 400 ms + borde 600 ms, idempotencia visual, skeleton, ARIA `aria-live`. | T51 | CA-02.1–CA-02.10 | RF-02, VIS-01..04 |
| T53 | VIS-05 Regional | Recharts `BarChart layout="vertical"`, 5 unidades en orden canónico, eje X `[0,max*1.15]`, grid solo horizontal, `LabelList right`, tooltip accesible, categoría sin datos (barra 0 + "sin datos"), unidad desconocida descartada. | T51 | CA-03.1–CA-03.6 | RF-03, VIS-05 |
| T54 | VIS-06 Turnos | Barras verticales con 3 turnos; color por estado (`cerrada` #0EA5E9, `en_curso` #38BDF8 + `EN CURSO`, `pendiente` #1E2A3D + `—`); tooltip con estado. | T51 | CA-04.1, CA-04.2 | RF-04.a–c, VIS-06 |
| T55 | VIS-07 Ranking Top 5 | Tabla semántica `<table>` 4 columnas (Posición/Comisaría/Intervenciones/Variación), hasta 5 filas ordenadas desc + desempate alfabético, badge de posición, destello de cambio de puesto, estado vacío `SIN DATOS`. | T51 | CA-04.3–CA-04.7 | RF-04.d–j, VIS-07 |
| T56 | Estados globales (§11.5) | Skeleton, EN VIVO, RECONECTANDO, DEGRADADO·POLLING, SIN CONEXIÓN, DATOS DESACTUALIZADOS (banner + opacidad 0,75), acceso denegado, error de esquema. Frescura por `last_event_ts` (>120 s). | T50, T52 | CA-05.5, CA-05.6, CA-05.8 | RF-05.g/h, §11.5 |
| T57 | Accesibilidad | Skip-link, foco visible (contorno 2 px #38BDF8), orden de tabulación, `aria-live`, tablas accesibles equivalentes, `prefers-reduced-motion`, objetivos táctiles 44×44 px. | T48, T52–T55 | CA-05.7, CA-05.4 | RNF-09, RF-05.i/l |
| T58 | Sanitización XSS + CSP estricta | Escape-by-default (sin `dangerouslySetInnerHTML`), catálogos fijos de etiquetas, CSP sin `unsafe-inline` en `script-src`, `frame-ancestors 'none'`. | T47, T52–T55 | CA-02.8, CA-03.3 | AM-06, AM-11, RF-03.h |

---

## Fase F8 — Observabilidad, auditoría y endurecimiento

| ID | Título | Descripción | Dep. | CA | RF/RNF |
|----|--------|-------------|------|----|--------|
| T59 | Trazas distribuidas OpenTelemetry | `trace_id` propagado del origen (Apps Script)→backend→cliente (`X-Correlation-Id` + `correlation_id`); una actualización rastreable extremo a extremo. | T17, T26, T50 | — | RNF-07.b |
| T60 | Alertas configurables | Reglas: p95 latencia >2 s, tasa rechazo >1 %, WSS a 0 con sala activa, reintentos de webhook agotados / último webhook >5 min, payload >64 KB, debounce SQL >1 %. | T21, T59 | — | RNF-07.d |
| T61 | Panel de salud de sala | Vista interna `platform-admin`: última actualización, estado del webhook (última recepción, reintentos), estado de réplicas/storage, edad del dato. | T21, T26 | — | RNF-07.e |
| T62 | Auditoría de lecturas | Registrar primera visualización por operador/día de datos (`sub`, `room_id`, `data_date`, `event_id`) y exportaciones; muestreo a bajo volumen (no por frame). | T26, T32 | CA-02.10 | RNF-08.e, AM-13 |
| T63 | Endurecimiento de cabeceras y anti-CSRF | Reforzar `X-Frame-Options`, `Cross-Origin-Opener-Policy`, `SameSite=Strict`, anti-CSRF en mutaciones, `no-store` en toda respuesta de datos. | T18, T50 | CA-05.1 | AM-11, AM-12, AM-10 |
| T64 | Limpieza de PII y secret scanning | Escanear logs/código: ausencia de PII y secretos; verificación de RNF-13 (nada en código de Apps Script/bundle/logs/repo). | T17, T42, T45 | — | RNF-08.c, RNF-13 |

---

## Fase F9 — Tests y verificación de criterios de aceptación

| ID | Título | Descripción | Dep. | CA | RF/RNF |
|----|--------|-------------|------|----|--------|
| T65 | pytest backend (unidad + integración) | Tests de ingesta/seguridad: `401` sin deserializar (firma HMAC inválida), cuerpo manipulado, anti-replay, idempotencia, rate limit, RBAC por capacidad, **verificación del webhook firmado de Apps Script / integración Google Sheets**, agregados "vs ayer", rollover de turnos. | T26, T37 | CA-01.2, CA-01.3, CA-01.6, CA-02.10 | RF-01, RNF-03/11/12 |
| T66 | Vitest/Jest frontend | Lógica de variación/formato (es-CL), ordenación ranking, turnos/estados, idempotencia visual, rechazo de KPI inválido, unidad desconocida. | T51–T55 | CA-02.3–CA-02.6, CA-03.2, CA-03.3, CA-04.2, CA-04.4, CA-04.6 | RF-02/03/04 |
| T67 | Playwright E2E | 7 visuales, mutación sin reload, WSS + reconexión + polling + cold start, flujo del webhook firmado E2E (payload de Apps Script simulado), estados de conexión, bounding boxes, orden de tabulación. | T52–T56 | CA-01.5, CA-02.1, CA-02.2, CA-02.7, CA-03.1, CA-03.4–CA-03.6, CA-04.1, CA-04.3, CA-04.5, CA-04.7, CA-05.1–CA-05.2, CA-05.4–CA-05.8 | RF-02..05 |
| T68 | axe-core accesibilidad + contraste | Auditoría WCAG 2.2 AA: sin violaciones críticas, contraste ≥4,5:1/≥3:1 con hex §11.2. | T57 | CA-02.8, CA-05.3, CA-05.7 | RNF-09 |
| T69 | Pruebas de carga k6 | Verificar p95 ≤1,5 s edición→visual, fan-out ≤100 ms, ≥50 WSS y ≥100 req/s por réplica, rate limits. | T26, T28, T30 | — | RNF-04, RNF-12 |
| T70 | Pruebas de seguridad | TLS 1.3 only, HSTS, headers, anti-replay, rate limit, **firma del webhook (rechazo sin firma o manipulada) / integración Google Sheets**, XSS (payload malicioso en celdas), CORS. | T18, T63 | CA-01.1, CA-01.2, CA-05.1 | RNF-01, AM-03/06/12 |
| T71 | Matriz de trazabilidad CA | Automatizar/verificar que los **40 CA** (CA-01.1 … CA-05.9) están cubiertos por al menos un test en verde y mapeados a tareas/RF/RNF/AM (cierre §15 sin huecos). | T65–T70 | *todos* | §15 |

---

## Fase F10 — Despliegue e infraestructura

| ID | Título | Descripción | Dep. | CA | RF/RNF |
|----|--------|-------------|------|----|--------|
| T72 | Docker backend + réplicas | Dockerfile optimizado; ≥3 réplicas sin estado (estado en Redis); *rolling deploy* sin corte. | T26, T28 | — | RNF-06.c |
| T73 | Cloudflare Pages + WAF + TLS | Deploy SPA (assets con hash, inmutables 1 año); WAF gestionado; rate limit edge por IP en `/ingest/webhook`; TLS 1.3. | T47 | — | RNF-01, RNF-12.e |
| T74 | IaC (PostgreSQL/Redis/auth-secrets/Google) | Terraform/Pulumi para PostgreSQL gestionado (PITR/failover), Redis, secret manager (secreto del webhook + `JWT_SIGNING_KEY`) y credenciales de la service account de Google (reconciliación de solo lectura sobre **cuenta Gmail estándar**). | T36 | — | RNF-06.d, RNF-13.a |
| T75 | CI/CD (staged) | Pipeline: build → test → secret scan → deploy SPA **antes** que backend (ventana 2 minors) → health gate. | T4, T65–T70 | — | §7.8, RNF-06 |
| T76 | Backups y DR (RNF-14) | PITR + snapshots diarios/semanales/mensuales cifrados (retención 35d/12sem/24m), clave distinta a producción, verificación de checksum y ensayo trimestral (incl. usuarios locales). | T74 | — | RNF-14 |
| T77 | Observabilidad producción + synthetic checks | Prometheus/Grafana, synthetic checks por minuto, historia de incidentes, failover ensayado. | T59, T72 | — | RNF-06.a, RNF-07.f |

---

## Resumen de dependencias críticas (reglas de oro)

- **Integración Google Sheets (F6)** no arranca hasta **F3** (`/ingest/webhook` + provisión/rotación del secreto).
- **Dashboard (F7)** no arranca hasta **F4** (cold start + WSS) y **F5** (auth JWT/RBAC).
- **Ningún secreto** se versiona en el código de Apps Script (T42), bundle (T49) ni repo (T4/T64); incluye `JWT_SIGNING_KEY` (T35).
- **Verificación final** = T71 cierra los 40 CA contra la spec antes de F10.
