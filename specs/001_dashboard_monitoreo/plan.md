# PLAN-001 — Plan de Implementación "Google Sheets-to-Web" + Dashboard de Monitoreo

**Spec de referencia:** `spec.md` (SPEC-001)
**Enfoque:** Zero Trust (Arquitectura de Seguridad Gubernamental)
**Fase SDD:** Fase 3 — Plan y Tareas (generado a partir de la spec aprobada)
**Stack:** Google Sheets + Google Apps Script (trigger + webhook HMAC) · FastAPI (REST + WSS + auth nativa JWT) · React 18 + Vite + Tailwind + Recharts (Cloudflare Pages) · PostgreSQL gestionado · Redis · Auth JWT (usuario+contraseña, sin MFA)

---

## 1. Objetivo y alcance del plan

Este plan descompone la SPEC-001 en un **orden de construcción verificable** que satisface los **5 requisitos funcionales** (RF-01 Transmisión Segura, RF-02 Tarjetas KPI, RF-03 Gráfico Regional, RF-04 Tendencia y Ranking, RF-05 UI Táctica), los **15 requisitos no funcionales** (RNF-01 … RNF-15), y cierra las **14 amenazas** (AM-01 … AM-14) mediante la cobertura de los **40 criterios de aceptación** (CA-01.1 … CA-05.9).

**Alcance funcional** (qué se construye):

- **Integración Google Sheets + Apps Script** (origen): trigger instalable (`onEdit`/`onChange`) sobre un único documento, normalización y validación del layout (cabeceras allowlist), hash de contenido (deduplicación), firma **HMAC-SHA256** y envío del webhook por HTTPS con reintentos (backoff 2 s → 60 s) y **reconciliación por polling de respaldo** (service account de solo lectura).
- **Backend FastAPI**: REST (ingesta webhook, cold start, histórico, salud, auth nativa login/refresh/logout y admin de usuarios locales) + WSS fan-out. **Verifica firma HMAC**, valida, persiste con idempotencia (`event_id`), agrega horarios/diarios, distribuye por Redis pub/sub, aplica rate limiting (200 req/min webhook), y auditoría append-only.
- **Autenticación nativa (FastAPI + PostgreSQL)**: login usuario/contraseña con hash **Argon2id** y bloqueo por intentos; emisión de JWT de acceso corto + refresh rotativo (reuse detection); roles `viewer`/`supervisor`/`auditor`/`platform-admin` mapeados a capacidades ortogonales.
- **PostgreSQL gestionado**: `ingest_event`, `snapshot_current`, `agg_hourly`, `agg_daily`, `ranking_snapshot`, `audit_event`, `webhook_registry`, `webhook_secret`, `role_capability` (PITR, failover, RPO 15 min / RTO 2 h).
- **Redis**: pub/sub, presencia, rate limit distribuido.
- **Dashboard React** (Vite + Tailwind + Recharts en Cloudflare Pages): 7 visuales (4 KPIs, regional barras horizontales, turnos barras verticales, ranking tabla Top 5), cold start REST + WSS, alto contraste dark.

**Decisiones ya resueltas** (aplicadas como invariantes del plan): TZ `America/Argentina/Buenos_Aires`; 3 turnos operativos (MAÑANA 06-14, TARDE 14-22, NOCHE 22-06); variación vs `ayer_mismo_tramo`; color por dirección; sesión sin expiración sala 24/7 (acciones sensibles auditadas, **sin MFA/step-up**); **auth nativa JWT (usuario+contraseña)**; una instancia = una sala; supervisor 90 d / auditor 60 m; volumen medio 100–1 000 ediciones/día; solo TLS 1.3; sin E2E navegador; PostgreSQL; barras verticales en turnos; mapeo Google Sheets 1:1 hojas→series (cuenta Gmail estándar); firma HMAC-SHA256 del webhook con rotación de secreto (solape 24 h).

**Fuera de alcance** (no se planifica): escritura desde dashboard, carga manual de datos, bidireccionalidad, PDF, app móvil, multi-tenant UI, SLA contractual de uptime, E2E navegador, IA/ML, geo-mapeo (OOS-01 … OOS-14).

---

## 2. Estrategia de implementación

El plan se construye **de abajo hacia arriba en capas de confianza**, de modo que cada capa se pueda verificar de forma aislada antes de que las capas superiores dependan de ella:

1. **Contratos primero** (F0): fijar el JSON Schema de mensajes (§7.8) y el contrato OpenAPI (§10) como *single source of truth*. Esto permite que backend, Apps Script y SPA se desarrollen en paralelo sin acoplarse a la implementación del otro.
2. **Datos y persistencia** (F1): el modelo relacional y el rol de servicio `svc_dashboard` de mínimo privilegio definen el contrato de escritura y lectura antes de escribir una sola línea de negocio.
3. **Backend de dentro hacia afuera** (F2 → F5): primero el núcleo y la seguridad transversal, luego la ingesta cifrada (el camino de entrada), luego la distribución (el camino de salida) y por último la identidad y el acceso nativo (JWT/RBAC), porque la autorización se comprueba en cada endpoint ya existente.
4. **Integración Google Sheets en paralelo tardío** (F6): la integración depende del endpoint de ingesta y de la provisión del secreto (F3), pero una vez disponibles puede desarrollarse en paralelo con el frontend.
5. **Frontend sobre un backend ya contratado** (F7): el dashboard consume cold start + WSS, ambos ya definidos y probados en F3–F4.
6. **Endurecimiento y verificación** (F8–F9): se cierran las amenazas y se demuestra la trazabilidad CA↔test antes de pasar a producción.
7. **Despliegue** (F10): infraestructura inmutable, CI/CD y recuperación ante desastres al final, cuando el sistema ya es estable.

**Por qué este orden:** (a) minimiza el *rework* al fijar contratos estables temprano; (b) permite **integración continua temprana** (F3 ya es "testeable" de punta a punta con un cliente simulado); (c) concentra los riesgos de identidad y de integración del origen en fases acotadas (F3, F5, F6) con tareas de seguridad explícitas; (d) garantiza que el frontend nunca tenga que "inventar" datos porque su backend ya está contratado y validado.

---

## 3. Fases del plan

| Fase | Objetivo | Entregable | Componentes implicados |
|------|----------|-----------|------------------------|
| **F0** | Fijar contratos y scaffolding del repo | JSON Schema de mensajes (§7.8), OpenAPI (§10), estructura monorepo, CI base, secret scanning | Repo, CI/CD, contrato de datos |
| **F1** | Modelo de datos y PostgreSQL | Migraciones de `ingest_event`, `snapshot_current`, `agg_hourly`, `agg_daily`, `ranking_snapshot`, `audit_event`, `webhook_registry`, `webhook_secret`, `role_capability`, `app_user`, `refresh_token`; rol `svc_dashboard` | PostgreSQL |
| **F2** | Backend núcleo y seguridad transversal | Config, `/health/*`, `/metrics`, logging estructurado sin PII, TLS 1.3 + HSTS + headers + CORS, rate limiting base, errores uniformes | FastAPI |
| **F3** | Ingesta segura | Verificación de firma HMAC-SHA256, anti-replay, validación de esquema/rangos, `POST /ingest/webhook` idempotente, provisión/rotación del secreto del webhook | FastAPI + PostgreSQL + crypto |
| **F4** | Distribución en tiempo real | Redis pub/sub fan-out por `room_id`, `seq` monotónico, `POST /auth/ws-ticket`, WSS `/ws/dashboard`, cold start, histórico, export CSV, auditoría | FastAPI + Redis |
| **F5** | Autenticación nativa JWT y RBAC | Usuarios locales + hash Argon2id, `POST /auth/login|refresh|logout`, gestión de usuarios locales (§10.6), middleware de capacidades | FastAPI + PostgreSQL |
| **F6** | Integración Google Sheets | Trigger Apps Script (`onEdit`/`onChange`), lectura/normalización de la hoja, hash de contenido, firma HMAC, webhook + reintentos, reconciliación por polling de respaldo, provisión/rotación del secreto | Google Sheets + Apps Script + FastAPI |
| **F7** | Dashboard React | 7 visuales (§11), WSS client + cold start, estados de conexión, accesibilidad, CSP/sanitización | React + Vite + Recharts |
| **F8** | Observabilidad, auditoría y endurecimiento | OpenTelemetry, alertas, panel de salud, auditoría de lecturas, CSP/headers, limpieza de secretos/PII | Backend + frontend |
| **F9** | Tests y verificación de CAs | pytest, Vitest/Jest, Playwright E2E, axe, k6, pruebas de seguridad, matriz de trazabilidad CA | Todo el sistema |
| **F10** | Despliegue e infraestructura | Docker + réplicas, Cloudflare Pages, IaC, CI/CD, backups RNF-14, observabilidad producción | Infraestructura |

---

## 4. Dependencias entre fases

```
F0 (contratos)
  └─► F1 (datos) ──► F2 (núcleo/seguridad) ──► F3 (ingesta) ──► F6 (Google Sheets)
                                        │              │
                                        │              └─► F4 (distribución) ──► F7 (dashboard)
                                        │                      │
                                        └──────► F5 (Auth JWT/RBAC) ─┘
                                                            │
                                    F8 (observabilidad/endurecimiento) ◄── F3+F4+F5+F7
                                                            │
                                    F9 (tests/verificación CA) ◄── todas las anteriores
                                                            │
                                    F10 (despliegue) ◄── F9
```

**Reglas de bloqueo explícitas:**

- **F1 bloquea F2/F3/F4/F5**: no se persiste ni se agrega sin esquema y rol de servicio.
- **F2 bloquea F3**: la ingesta asume rate limiting, headers de seguridad, logging y errores uniformes ya existentes.
- **F3 bloquea F6**: la integración no puede publicar sin `POST /ingest/webhook` ni configurarse sin la provisión del secreto.
- **F3+F4 bloquean F7**: el dashboard consume cold start (F4) y WSS (F4) y asume que la ingesta (F3) produce eventos válidos.
- **F5 bloquea F7 (autenticado) y F4 (ticket/RBAC)**: el WSS exige ticket ligado a `sub` + capacidades; el RBAC por capacidad se comprueba en cada endpoint y en la apertura del WSS.
- **F6 y F7 pueden solaparse** una vez que F3/F4/F5 están contratadas (desarrollo paralelo Apps Script ⇄ frontend).
- **F8 depende de F3+F4+F5+F7** (observar lo ya existente); **F9 depende de todas**; **F10 es el último** (despliega un sistema ya verificado).

---

## 5. Riesgos del plan

| # | Riesgo | Impacto | Mitigación en el plan |
|---|--------|---------|-----------------------|
| R1 | **Deriva de contrato** backend↔Apps Script↔SPA durante desarrollo paralelo | Pantalla en blanco / ingesta rota | F0 fija JSON Schema + OpenAPI como fuente única; CI valida ejemplos contra el schema; ventana de soporte de 2 minors (§7.8) |
| R2 | **Firma del webhook mal implementada o secreto filtrado** (comparación no constante, secreto versionado en el código) | Compromiso de la cadena de ingesta | Tareas F3/F6 dedicadas a HMAC-SHA256 + comparación en tiempo constante + secreto en secret manager/`Script Properties`; rotación con solape; secret scanning en CI; prueba CA-01.1/CA-01.3 |
| R3 | **Fiabilidad del trigger de Apps Script y cuotas/rate limits de Google Sheets API** | Falsos negativos/duplicados | F6: trigger instalable + reconciliación por polling de respaldo 60 s + coalescencia 750 ms + deduplicación por hash; permisos de la **cuenta estándar de Google** verificados; prueba con ediciones reales (RISK-01, RISK-14, RISK-15) |
| R4 | **Rollover de turnos y DST** (turno NOCHE cruza medianoche) | Variaciones erróneas | F4/F7: cálculo en backend con TZ canónica y `data_date`+`turno_id`; `estado` pendiente/en_curso/cerrada (RF-04.b, RISK-03/RISK-11) |
| R5 | **CSP estricta vs Recharts/Tailwind** (estilos inline) | Debilitar AM-06/AM-11 | F7/F8: CSP sin `unsafe-inline` en `script-src`; test E2E que falla si aparece `unsafe-inline` (RISK-07) |
| R6 | **"vs ayer" costoso** si se recalcula por petición | Latencia > p95 | F4: precalcular baselines/variación en backend y cachear por `data_date`+`turno_id` (RISK-05) |
| R7 | **Gestión de credenciales locales y rotación de `JWT_SIGNING_KEY`** (OD-05) | Compromiso de credenciales o rotación no coordinada degrada la autenticación de todos los operadores | F5: Argon2id + bloqueo por intentos + rate limit de login; `JWT_SIGNING_KEY` en secret manager con rotación 90 días y solape de validación; backups cifrados del almacén local (RISK-13, RNF-14.f) |
| R8 | **Fan-out WSS bajo carga** (50 conexiones/sala) | Actualizaciones perdidas/latencia | F4: fan-out por `room_id` en Redis, `seq` monotónico, cold start para rellenar huecos (RISK-04) |
| R9 | **Alcance 24/7 vs seguridad de sesión** | Logouts molestos o credenciales largas | F5/F7: sin expiración en sala + refresh rotativo con actividad, **sin MFA/step-up**; acciones sensibles auditadas (OD-04, RISK-09) |
| R10 | **Retraso de integración tardía** (todo se junta al final) | Bugs de integración al final | F9 temprano: CI corre pytest+Vitest desde F2/F3; integración continua por fase, no big-bang |
| R11 | **Permisos OAuth de la cuenta estándar de Google** (la service account o el script pierde acceso al documento) | El trigger no puede leer o notificar | F6: verificación de permisos al arrancar la reconciliación; alerta de salud del origen; polling con service account de solo lectura; ensayo de rotación (RISK-15) |
| R12 | **Rate limit / cuota de la API de Google Sheets** en picos de edición | Retraso o pérdida de la notificación | F6: reintentos con backoff; coalescencia de ediciones; reconciliación por polling; alerta si el último webhook supera el umbral (RNF-07.d) |

---

## 6. Criterios de done globales

El plan se considera **completo** cuando se cumplen, de forma **verificable**:

1. **Cobertura de RF**: los 5 RF (RF-01 … RF-05) están implementados y demostrados por al menos un test automatizado cada uno.
2. **Cobertura de RNF**: los 15 RNF (RNF-01 … RNF-15) están implementados y medidos según su columna "Medición" (§6).
3. **Cobertura de amenazas**: las 14 amenazas (AM-01 … AM-14) tienen mitigación implementada y un CA que la verifica (matriz §15 sin huecos).
4. **Cobertura de CA**: los **40 criterios de aceptación** (CA-01.1 … CA-05.9) pasan en verde; la matriz de trazabilidad CA↔test↔tarea está completa y automatizada (tarea de F9).
5. **Visuales**: los 7 visuales (VIS-01 … VIS-07) renderizan con datos reales de contrato y cumplen la especificación visual normativa (§11).
6. **Latencia**: p95 ≤ 1,5 s (p99 ≤ 3 s) edición→visual, cold start ≤ 1,5 s, fan-out WSS ≤ 100 ms (p95), medido con k6 + `performance.now()`.
7. **Seguridad**: TLS 1.3 únicamente, HSTS, CSP estricta, no-store, anti-replay, rate limiting, firma HMAC-SHA256 del webhook, y **ningún secreto** en el código de Apps Script, el bundle, los logs ni el repositorio (secret scanning activo).
8. **Accesibilidad**: WCAG 2.2 AA — axe-core sin violaciones críticas y contraste ≥ 4,5:1 / ≥ 3:1 verificado.
9. **Recuperación**: backups cifrados + PITR con RPO 15 min / RTO 2 h, y ensayo de restauración documentado (RNF-14).
10. **Despliegue**: SPA (Cloudflare Pages) y backend (Docker, ≥ 3 réplicas) desplegables desde CI/CD con *rolling deploy* sin corte para el dashboard.
