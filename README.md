# Google Sheets-to-Web — Dashboard de Monitoreo

Sistema de **sincronización en tiempo real** de indicadores institucionales ("Google Sheets-to-Web"): detecta las ediciones guardadas en un documento de Google Sheets fuente (SIFCOP) mediante un trigger de Apps Script, las transmite firmadas con HMAC-SHA256 a un backend que verifica identidad e integridad en cada salto, las archiva como historial consultable y las redistribuye en tiempo real a dashboards web autenticados y autorizados, con un contrato visual táctico de alto contraste para salas de operaciones.

> **Nota de seguridad:** este es un proyecto **Zero Trust** de seguridad gubernamental. Los datos son sensibles (dominio restringido) y toda comunicación, identidad y decisión de autorización se verifica explícitamente en cada salto. Ningún secreto se versiona, se registra ni se embebe en el código del origen o en el bundle del navegador. Ver la spec para el modelo completo de amenazas y contramedidas.

## Especificación

- **Spec:** [`specs/001_dashboard_monitoreo/spec.md`](specs/001_dashboard_monitoreo/spec.md)
- **Plan:** [`specs/001_dashboard_monitoreo/plan.md`](specs/001_dashboard_monitoreo/plan.md)
- **Tareas:** [`specs/001_dashboard_monitoreo/tasks.md`](specs/001_dashboard_monitoreo/tasks.md)

## Estructura del monorepo

```
excel-sync-gov/
├── backend/          # FastAPI (REST + WebSockets) — frontera de confianza
│   ├── app/          # aplicación (api, services, models, core)
│   ├── alembic/      # migraciones (PostgreSQL)
│   └── docs/         # esquema y seguridad
├── apps-script/      # Origen Google Sheets (Apps Script: trigger + webhook HMAC)
├── dashboard/        # React (Vite + Tailwind + Recharts) en Cloudflare Pages
├── infra/            # IaC (Docker, Terraform/Pulumi, secret manager)
├── contracts/        # JSON Schema de mensajes + OpenAPI (fuente única de contrato)
├── specs/            # Especificación, plan y tareas (SDD)
├── docs/             # documentación transversal
└── .github/          # CI/CD (lint, typecheck, secret scanning)
```

### Convenciones de layout

- Un directorio de primer nivel por componente desplegable (`backend/`, `apps-script/`, `dashboard/`, `infra/`); los contratos y la especificación son transversales (`contracts/`, `specs/`, `docs/`).
- Cada componente es autocontenido: su build, tests y configuración de herramienta viven en su directorio. El tooling Python del backend se centraliza en el `pyproject.toml` raíz (fuente de verdad de `ruff`/`black`/`mypy`).
- El código del backend se organiza por capas (`app/api`, `app/services`, `app/models`, `app/core`); el frontend por funcionalidad y las migraciones por revisión (`backend/alembic/versions/`).
- Los componentes NO comparten imports entre sí: se integran exclusivamente a través de `contracts/`.
- `.env` nunca se versiona; solo las plantillas `.env.example` (sin valores reales). El origen Apps Script no usa `.env`, sino `Script Properties`.

### Contratos: rutas y versionado

`contracts/` es la **fuente única de verdad** que permite desarrollar backend, Apps Script y dashboard en paralelo:

- **Mensajes WSS:** `contracts/messages/<semver>.schema.json` (p. ej. `contracts/messages/1.0.0.schema.json`), con al menos un ejemplo válido de la misma versión (`contracts/messages/<semver>.example.json`) que CI valida contra el schema.
- **API REST + WSS:** `contracts/openapi.yaml` (única fuente de endpoints, errores y canal WSS).
- **Versionado:** cada archivo de versión es **inmutable**; todo cambio publica un archivo nuevo siguiendo semver `MAJOR.MINOR.PATCH` (rompedor = MAJOR, aditivo = MINOR, editorial = PATCH).
- **Compatibilidad:** el backend soporta las **dos últimas minors** en coexistencia durante los despliegues (política de 2 minors); los schemas de esas minors se conservan en el repo y el dashboard se despliega antes que el backend.
- Reglas detalladas en [`contracts/README.md`](contracts/README.md) y en la spec §7.8.

## Stack tecnológico

| Componente | Tecnología |
|------------|------------|
| Origen de datos | Google Sheets · Google Apps Script (trigger `onEdit`/`onChange` + webhook firmado HMAC-SHA256) · `UrlFetchApp` (reintentos con backoff) · `Script Properties` |
| Backend | FastAPI · REST + WebSockets Seguros (WSS) · Redis (pub/sub + presencia) · PostgreSQL |
| Dashboard | React 18 · Vite · Tailwind CSS · Recharts · Cloudflare Pages |
| Identidad | Auth nativa JWT (usuario+contraseña, Argon2id; sin IdP externo ni segundo factor) |
| Datos | PostgreSQL (historiales, agregados, auditoría append-only) |
| Infraestructura | Docker · Terraform/Pulumi · secret manager · Cloudflare (WAF + TLS 1.3) |

## Enfoque Zero Trust

El sistema aplica los principios *never trust, always verify*, mínimo privilegio, defensa en profundidad y *fail-closed*:

- **Apps Script → Backend:** webhook firmado con **HMAC-SHA256** (secreto versionado por `key_id`, custodiado en `Script Properties` + secret manager), TLS 1.3, anti-replay (nonce + timestamp) y verificación de firma antes de deserializar.
- **Operador → Dashboard:** login nativo usuario+contraseña contra el backend, JWT de vida corta (15 min), refresh token rotativo con detección de reutilización, autorización por **capacidades ortogonales** (no por roles cerrados).
- **Backend → Almacén:** identidad de servicio `svc_dashboard` de mínimo privilegio, cifrado en reposo y auditoría **append-only**.
- **Cliente:** el navegador es un consumidor no confiable; nunca recibe secretos ni datos crudos (solo agregados autorizados por rol).

Para el detalle normativo (requisitos EARS, RNF, modelo de datos, contrato de API y criterios de aceptación), consultar la spec enlazada arriba.
