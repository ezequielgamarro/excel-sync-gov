# INFORME GENERAL DEL PROYECTO — `excel-sync-gov`

> Relevamiento de todo el repositorio (especificación, backend, Apps Script, dashboard, infra/CI) y de los dos módulos de Excel. Fecha del informe: 05/10/2026. Todo dato marcado como "verificado" se comprobó contra el código y/o el servidor en ejecución.

---

## 1. Resumen ejecutivo

Sistema **Google Sheets-to-Web + Dashboard de Monitoreo** (norma: `specs/001_dashboard_monitoreo/spec.md`). Detecta ediciones de un Google Sheets institucional vía Apps Script, las transmite firmadas con **HMAC-SHA256**, las verifica/almacena/redistribuye en tiempo real (WSS) a dashboards autenticados, con enfoque **Zero Trust**.

| Área | Estado |
|---|---|
| Especificación / plan / tareas | Completa (spec 161 KB, 77 tareas T1–T77, fases F0–F10) |
| Contratos (OpenAPI + JSON Schema) | Completa y validada en CI |
| Apps Script (origen) | **Implementado** (10 `.gs`), sin deploy automatizado |
| Backend FastAPI | **Muy completo** (~30 endpoints, 14 migraciones, 146 tests) con brechas de seguridad y features sin cablear |
| Dashboard React | Base sólida; **gran parte de los gráficos usa datos demo/fabricados**; 2 módulos de Excel reales integrados |
| Infra / CI / observabilidad | IaC y pipelines escritos; **falta cableado real** a orquestador/secret manager |
| Tests | Backend 146 funciones; Frontend ~73 Vitest + E2E Playwright; **no ejecutados los de F9 en este entorno** |
| Estado Git | **Sin commits** (`refs/heads` y `.git/index` vacíos) |

**El proyecto NO está terminado**: hay funciones reales funcionando, pero quedan pendientes operativos (despliegue real, cifrado en reposo, datos demo en el dashboard, DR) y documentación desactualizada.

---

## 2. Qué es el sistema y su alcance

**Propósito:** el sistema SIFCOP publica cifras en un Google Sheets editado a mano; la web las sincroniza en tiempo real, con trazabilidad, auditoría y control de acceso.

**En alcance (spec §4.1):** trigger `onEdit`/`onChange`, webhook HMAC-SHA256 con rotación, backend FastAPI, reconciliación por polling, PostgreSQL idempotente, dashboard React, auth nativa JWT, WSS, i18n es.

**Fuera de alcance (OOS-01..OOS-14):** escritura desde el dashboard, carga manual, escritura de vuelta a Sheets, PDF, app móvil, multi-tenant, E2E navegador↔origen, IA/ML, geo-mapeo, SSO/MFA, SLA contractual.

**Requisitos:** 5 RF (transmisión, KPIs, regional, turnos/ranking, UI táctica), 15 RNF, 14 amenazas STRIDE, **40 criterios de aceptación** (CA-01.1 … CA-05.9).

---

## 3. Arquitectura por componentes

```
Google Sheets ──(Apps Script: trigger + HMAC)──▶ FastAPI ──▶ PostgreSQL / Redis ──▶ WSS ──▶ Dashboard React
                                                   │
                                        (módulos Excel directos)
                                  /api/estadisticas      (hoja DASHBOARD_WEB, policial)
                                  /api/hospitales/...    (planilla de hospitales)
```

Documentación rectora: `specs/001_dashboard_monitoreo/{spec,plan,tasks}.md` · `contracts/openapi.yaml` + `contracts/messages/1.0.0.schema.json` · `docs/{traceability,secrets}.md`.

---

## 4. Estado por componente

### 4.1 Especificación, plan y tareas
- **SPEC-001**: completa, 8 objetivos, 7 visuales, 40 CA, 15 decisiones abiertas **resueltas**.
- **plan.md**: estrategia "de abajo hacia arriba en capas de confianza", fases **F0–F10**.
- **tasks.md**: **77 tareas (T1–T77), todas con artefactos de código**. ⚠️ El documento **no tiene columna de estado ni checkboxes**: ninguna tarea figura formalmente "completada"; hay que inferirlo del repo.
- **SPEC-003** (`specs/003_excel_sync_gov/spec.md`): sistema **distinto** (agente local + Cloudflare R2 + OIDC). **No implementado**: el repo pivoteó a SPEC-001 (evidencia: `backend/app/api/agents.py:17-19`). Sin `plan.md`/`tasks.md`, **12 decisiones abiertas sin resolver** y **texto corrupto/ofuscado** en varias líneas (p. ej. `:14,19,30,476`). Deuda documental.
- **`docs/secrets.md`** está **parcialmente obsoleto** (describe el agente/DPAPI de SPEC-003, ya retirado).

### 4.2 Backend FastAPI — **lo más maduro**
- Composición en `app/main.py`: pila de middlewares `CORSVary → CORS → CorrelationId → Tracing → SecurityHeaders → CSRF → Metrics → RateLimit → RBAC → app`, deny-by-default.
- **~30 endpoints**: ingesta firmada, snapshot/history/consultas/export.csv, auditoría, auth nativa (login/refresh/logout/ws-ticket), admin usuarios/roles, health/metrics, WSS, más los 2 módulos Excel públicos.
- Servicios: ingesta idempotente, agregados "vs ayer", HMAC, anti-replay, revocación, reconciliación, salud de origen/sala, alertas, JWT nativo, Argon2id, rate limit token-bucket, bus Redis.
- **Modelo de datos**: 13 tablas proyectadas + 14 migraciones Alembic (particionado, auditoría append-only con trigger, rol `svc_dashboard`).
- **Tests**: **146 funciones en 22 archivos** (sin `conftest.py`; muchos con stubs).
- **Sin `TODO`/`FIXME`/`NotImplemented`**.

### 4.3 Apps Script (origen) — **completo**
10 archivos `.gs` implementados: config con catálogos cerrados, utilidades (SHA-256/UUIDv7), custodia del secreto en `Script Properties`, lector de hojas (fail-closed), digest, firmante HMAC-SHA256, cliente con backoff, triggers instalables (`onEdit`/`onChange` + reintento 1/min), salud con anti-fuga y autotest. Firma: `HMAC-SHA256(secreto, "{webhook_id}|{key_id}|{nonce}|{timestamp}|{schema_version}|{sha256(cuerpo)}")`.
**Falta:** deploy automatizado (no hay `.clasp.json`), provisión/rotación del secreto es manual, la salud no se empuja periódicamente.

### 4.4 Dashboard React
**Real (consume backend):** snapshot en vivo (KPIs, regional, turnos, ranking), módulo **hospitales** y módulo **DASHBOARD_WEB** (ver §6).
**Fabricado/demo (deuda):**
- `components/charts/demoSeries.ts` — series demo deterministas (turnos 1250/1650/850, categorías fijas, PRNG).
- `lib/barData.ts:44-96` — multiplicadores que falsean datos reales (`RANGO_SCALE`, `PERIOD_SCALE`, `TURNO_CROSS`, `UNIDAD_CROSS`).
- `lib/comparison.ts:28-48` — baselines de semana/mes/año inventadas (solo "Ayer" es real).
- `RealtimeEventsChart.tsx:99-116` — agrega un punto sintético por segundo (sinusoide).
- `DistributionDonutChart.tsx` y `TurnosColumnsChart.tsx` — usan demo/multiplicadores porque **nunca reciben sus props `groups`/`series`**.
- `RecentRecordsTable.tsx` — 100% inventado y **código muerto**.
- `hooks/useConsultas.ts` + `GET /dashboard/consultas` — **implementados y nunca usados**.

### 4.5 Infra / CI / observabilidad
**Implementado:** Docker/Swarm (`docker-compose.yml`, `docker-stack.prod.yml`, `rollout.sh`), Terraform (VPC, Cloud SQL, Memorystore, Secret Manager, KMS+backups, Cloudflare TLS1.3/WAF), Cloudflare Pages, Prometheus/Grafana/synthetic, backups con `pg_dump`+AES, workflows `ci.yml`/`secret-scan.yml`/`deploy.yml`, k6 (webhook, REST, WSS), scripts de contrato/PII.
**Incompleto:** `deploy.yml` **no está cableado** a un orquestador real ni al secret manager; no hay job de `terraform apply`, migraciones, k6 ni Apps Script; `versions.tf` tiene `REPLACE_ME-terraform-state`; solo ~2 de ~11 secretos tienen versión en Terraform; falta manifiesto ejecutable del stack de observabilidad y `blackbox.yml`; falta scheduler de backups; `incident-history.md` marca `_pendiente_` los ensayos de DR; rate limit inconsistente (spec/k6 200/min vs Cloudflare 120/min).

### 4.6 Tests / verificación
- Backend: 146 funciones; **pero T65/T67/T68/T69 (pytest/Playwright/axe/k6) no se ejecutaron** en este entorno (`docs/traceability.md:80`).
- Frontend: Vitest (última corrida ~73 tests verdes) + E2E Playwright (mayormente con backend simulado; `webhook.spec.ts` se auto-omite sin backend real).
- **Sin cobertura:** Admin API, auth HTTP end-to-end, WebSocket, `/dashboard/consultas`, `user_store`, persistencia real, migraciones, composición de la app.

---

## 5. Lo que SÍ se hizo

1. Especificación/plan/tareas + contratos (OpenAPI, JSON Schema) validados en CI.
2. Apps Script completo con HMAC, rotación de clave con solape 24 h, anti-replay, triggers instalables y autotest.
3. Backend completo: ingesta idempotente, RBAC por capacidades, JWT nativo con reuse detection, auditoría append-only, particionado, rate limiting, hardening, OTel/Prometheus.
4. Dashboard con auth nativa, WSS + cold start + degradación a polling, reducer idempotente, validación defensiva, PWA, a11y y diseño táctico.
5. IaC + Docker + Cloudflare + observabilidad + backups + k6 + CI/CD (escritos).
6. **Dos módulos de Excel reales integrados** (ver §6) y **verificados en vivo**.

---

## 6. Módulos de Excel (estado verificado)

### (a) Sheet policial — `EXCEL_POLICIA_URL` → `GET /api/estadisticas`
- Lee la hoja `DASHBOARD_WEB` con pandas; devuelve `grafico_regionales`, `grafico_dependencias`, `alertas_resultados`.
- **Verificado en vivo:** `HTTP 200`, `estado=exito`. Hoy: `POSITIVO=28`, `NEGATIVO=337`, 7 regionales, 36 dependencias.
- **Integración:** componente `EstadisticasSection` + `hooks/useEstadisticas.ts` + `components/estadisticas/*`, renderizado en el tab **"Resumen General"** (no en el tab "Estadísticas", que sigue siendo demo). Sin datos demo: en error muestra error.

### (b) Planilla de hospitales — `HOSPITALES_SHEET_URL` → `GET /api/hospitales/estadisticas`
- Lee la **primera pestaña** del Google Sheets (`to_export_url`).
- **Verificado en vivo:** `sheet=Hoja1`, `total_rows=31`; **sin suma doble** (la fila de totales se excluye): `lesiones_culposas=30`, `heridos_arma_fuego=2`, `violencia_familiar=2`; `chartData` poblado.
- **Integración:** tab **"Ingresos Hospitalarios"** (`HospitalDashboard` + `useHospitales` + `components/hospitales/*`).
- **Detalles flojos pendientes:** encabezados vacíos se muestran como `col_9`, `col_11`…; `homicidios=0` aunque existen "Homicidios Culposos" (3) y "Tentativa de Homicidios" (1).

### Patrón repetible para agregar un Excel nuevo
1. Compartir el Sheets como "cualquiera con el enlace"; cargar la URL en `.env` (`NUEVO_EXCEL_URL`).
2. Backend: copiar `hospitales.py` → `api/<nombre>.py`, adaptar columnas/KPIs; montar en `main.py` con prefijo `/api/<nombre>`; declarar **PUBLIC** en `core/rbac.py`.
3. Frontend: `fetch<Nombre>()` en `data/api.ts` + `hooks/use<Nombre>.ts`.
4. Vista: `screens/<Nombre>Dashboard.tsx` + ítem en `AdminSidebar` + hash en `DashboardScreen`.

---

## 7. Lo que NO se hizo / queda pendiente (con evidencia)

**Alta prioridad (seguridad / funcional):**
1. **Cifrado en reposo NO implementado.** `services/ingest.py:229` guarda `payload_ciphertext=raw_body` (bytes crudos). `kek_material`/`data_key` declarados y sin uso → incumple RNF-02.a.
2. **`agent_id` nunca se persiste** en la ingesta (`ingest.py:248-269`) → el cold start devuelve `source.webhook_id=""` (`dashboard.py:114`), rompiendo trazabilidad.
3. **Presencia WSS desconectada:** `room_health` reporta siempre 0 (`bus.py:290-328` vs `ws.py`).
4. **Datos demo/fabricados en el dashboard** (Incidentes, Logística, Estadísticas, Comparativas) — §4.4.
5. **`.env` con credenciales y URLs reales** (`.env`, líneas 1–11). Está en `.gitignore` y el repo **no tiene commits**, pero hay riesgo si se hace `git add -f`.

**Media:**
6. Capacidades muertas `platform.rotate_secrets` y `platform.replay` (sin endpoint); métrica `INGEST_EVENTS` sin uso.
7. Tablas/modelos huérfanos (`keyring` sin migración; `agent_registry` no proyectada); deriva entre `docs/schema.md`, `alembic/README.md` y el código.
8. Rate limit **por IP** en vez de `sub` (`docs/security.md` desactualizado).
9. Reconciliación/health monitor **desactivados por defecto** (`config.py:163`).
10. `/api/estadisticas` y `/api/hospitales` devuelven **HTTP 200 con `estado:"error"`** en fallos.

**Documentación / verificación:**
11. `tasks.md` **sin estado**; no hay `CHANGELOG`/`STATUS`.
12. Tests F9 **no ejecutados** (pytest/Playwright/axe/k6).
13. Ensayos **DR pendientes** (`incident-history.md:26-28`: failover PG, restore backup, Redis).
14. SPEC-003 sin plan/tasks, sin aprobar y con texto corrupto; `docs/secrets.md` obsoleto; `dashboard/README.md` desactualizado.
15. `src/components/DashboardPolicia.jsx` (raíz) **huérfano** (prototipo previo; no referenciado).

**Producción (infra):**
16. `deploy.yml` sin orquestador/secret manager; sin Terraform apply/migraciones/k6/Apps Script en CI; placeholders (`REPLACE_ME-terraform-state`, `example.gov`); versiones de secretos incompletas; observabilidad no ejecutable; scheduler de backups ausente; rate limit inconsistente.

---

## 8. Riesgos principales

| # | Riesgo | Severidad |
|---|---|---|
| 1 | Datos sensibles sin cifrar en BD (invoca RNF-02.a) | Crítica |
| 2 | Datos demo mostrados como reales en sala (riesgo de decisión errónea) | Alta |
| 3 | `.env` con credenciales/URLs reales | Alta |
| 4 | Sin commits → riesgo de versionar secretos o perder trabajo | Alta |
| 5 | Pipeline de deploy no cableado (no desplegable a prod hoy) | Alta |
| 6 | Sin ensayos de recuperación (RPO/RTO sin verificar) | Media |
| 7 | Deriva documental (schema/secrets/README/tasks) | Media |

---

## 9. Roadmap sugerido hacia producción

1. **Seguridad:** implementar cifrado de aplicación (envelope con KEK/DEK) o retirar la afirmación del contrato; persistir `agent_id`; rate limit por `sub`.
2. **Datos:** eliminar fallbacks demo del dashboard o marcarlos explícitamente; cablear `useConsultas` en Incidentes/Logística/Estadísticas.
3. **Repo:** primer commit con `.env` verificado como ignorado; **rotar** credenciales/URLs expuestas.
4. **Deploy:** cablear `deploy.yml` al orquestador + secret manager; agregar Terraform apply, Alembic y health-gate sobre `/health/ready`.
5. **Observabilidad/DR:** manifiesto ejecutable del stack, `blackbox.yml`, recording rule `alert_active`; scheduler de backups + ensayos trimestrales.
6. **Verificación:** ejecutar pytest/Playwright/axe/k6; cerrar los 40 CA.
7. **Documentación:** actualizar `tasks.md` con estado, `docs/secrets.md`, `dashboard/README.md`; decidir SPEC-003 (archivar o implementar).
