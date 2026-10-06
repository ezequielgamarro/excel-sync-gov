# Esquema de datos — Google Sheets-to-Web (Fase F1, T8–T15)

Modelo relacional PostgreSQL del sistema **Google Sheets-to-Web** (SPEC-001).
Fuente autoritativa: `specs/001_dashboard_monitoreo/spec.md` **§7 (Modelo de
datos)**, especialmente **§7.9 (almacenamiento)** y **§2.2.4 (mínimo privilegio)**.

Se implementa con migraciones Alembic en `backend/alembic/versions/`
(`0002`→`0009`, encadenadas sobre `0001_base`). Esquemas: `app` (operativo) y
`audit` (append-only).

---

## 1. Diagrama ER textual (10 tablas)

```
┌─────────────────────────────────────────────────────────────────────────┐
│ app (operativo)                                                          │
│                                                                          │
│  ingest_event (part. mes · 90 d)                                         │
│  ├─ event_id  uuid        ──────────────────────┐                        │
│  ├─ doc_id    text                              │  FK lógica             │
│  ├─ webhook_id text  ──────────┐                │                        │
│  ├─ content_sha256 text        │                │                        │
│  ├─ payload_ciphertext bytea   │                │                        │
│  ├─ seq       bigint           │                │                        │
│  ├─ received_at timestamptz    │                │                        │
│  └─ correlation_id text        │                │                        │
│                                │                │                        │
│  webhook_registry              │                │                        │
│  ├─ webhook_id text PK ◄───────┘                │                        │
│  ├─ doc_id    text                              │                        │
│  ├─ estado    text (activo/revocado)            │                        │
│  ├─ revoked_at / created_at / last_seen_at      │                        │
│                                │                │                        │
│  snapshot_current (1 fila/doc) │                │                        │
│  ├─ doc_id  text PK            │                │                        │
│  ├─ event_id uuid ◄─────────────────────────────┘                        │
│  ├─ payload jsonb (en claro)                                              │
│  ├─ data_date date · seq bigint · updated_at                              │
│                                                                          │
│  agg_hourly (part. mes · 60 m)        agg_daily (part. mes · 60 m)        │
│  ├─ bucket timestamptz PK            ├─ bucket date PK                    │
│  ├─ kpi_id text PK                   ├─ kpi_id text PK                    │
│  ├─ unidad_id text ('' = n/a)        ├─ unidad_id text                    │
│  ├─ turno_id  text ('' = n/a)        ├─ turno_id  text                    │
│  ├─ value bigint                     ├─ value bigint                      │
│  └─ baseline_value bigint            └─ baseline_value bigint             │
│                                                                          │
│  ranking_snapshot (part. mes · 60 m)  webhook_secret (permanente)         │
│  ├─ data_date date PK               ├─ key_id  text PK                    │
│  ├─ turno_id  text PK               ├─ webhook_id text FK lógica          │
│  ├─ puesto    int PK                ├─ estado text (vigente/rotada/revocada)│
│  ├─ dependencia_id text UNIQUE      ├─ not_before / not_after (solape 24 h)│
│  ├─ comisaria text                  └─ created_at / rotated_at             │
│  ├─ intervenciones bigint                                                 │
│  ├─ variacion_abs bigint                                                 │
│  ├─ variacion_pct numeric(8,2)                                           │
│  └─ puesto_previo int                                                     │
│                                                                          │
│  role_capability (configurable)                                          │
│  ├─ role text PK · capability text PK · granted bool                      │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│ audit (append-only)                                                      │
│  audit_event (part. mes · 60 m)                                          │
│  ├─ id bigint (seq audit.audit_event_id_seq)                             │
│  ├─ ts timestamptz · actor · action · resource · result                  │
│  └─ ip (seudonimizada) · user_agent · correlation_id · schema_version    │
└─────────────────────────────────────────────────────────────────────────┘
```

**Relaciones:**

| Desde | Hacia | Tipo | Nota |
|-------|-------|------|------|
| `ingest_event.webhook_id` | `webhook_registry.webhook_id` | FK lógica (sin CONSTRAINT) | `webhook_registry` no está particionado; se documenta, no se fuerza. |
| `webhook_secret.webhook_id` | `webhook_registry.webhook_id` | FK lógica (sin CONSTRAINT) | Cada origen/despliegue tiene su propio `webhook_id`; la revocación es individual. |
| `snapshot_current.event_id` | `ingest_event.event_id` | FK lógica | `ingest_event` está particionado: PostgreSQL no admite FK hacia tablas particionadas. |
| `agg_*` / `ranking_snapshot` | `ingest_event` | Derivadas | Se agregan en el backend a partir de cada evento aceptado; no hay FK. |

> **Por qué FK lógicas:** el particionado y la idempotencia (alta tasa de
> escritura, retención por mes) hacen que las FK físicas sean inviables o
> contraproducentes. La integridad se garantiza en la capa de aplicación
> (T26: verificación de firma HMAC → descifrado → INSERT idempotente →
> agregados).

---

## 2. Tablas y columnas clave por tarea

### T8 — `app.ingest_event` (cabecera de cada evento, 90 días)

| Columna | Tipo | Regla |
|---------|------|-------|
| `event_id` | `uuid` | UUIDv7, **clave de idempotencia**. Generado en el origen (Apps Script). `UNIQUE (event_id, received_at)` (la clave de partición exige incluir `received_at`). |
| `doc_id` | `text` | Documento de Google Sheets declarado. |
| `webhook_id` | `text` | FK lógica → `webhook_registry.webhook_id`. Identifica el origen. |
| `content_sha256` | `text` | 64 hex (`CHECK ~ '^[0-9a-f]{64}$'`). |
| `payload_ciphertext` | `bytea` | AES-256-GCM; clave en secret manager, nunca en BD. |
| `seq` | `bigint` | Monótono (asignado por el backend). |
| `received_at` | `timestamptz` | Instante de aceptación (partición). |
| `correlation_id` | `text` | Correlación extremo a extremo. |

### T9 — `app.snapshot_current` (1 fila/doc, cold start)

`doc_id` (PK) · `event_id` (FK lógica) · `payload` (`jsonb`, en claro) ·
`data_date` (`date`) · `seq` (`bigint`) · `updated_at`.

### T10 — `app.agg_hourly` + `app.agg_daily` (60 meses)

`bucket` (`timestamptz` hora / `date` día) · `kpi_id` · `unidad_id` ('' si n/a) ·
`turno_id` ('' si n/a) · `value` (`bigint`) · `baseline_value` (`bigint` NULL).
PK `(bucket, kpi_id, unidad_id, turno_id)`. `agg_daily` alimenta `baseline_value`.

### T11 — `app.ranking_snapshot` (Top 5, 60 meses)

`data_date` · `turno_id` · `puesto` (1..5) · `dependencia_id` · `comisaria` ·
`intervenciones` · `variacion_abs` · `variacion_pct` (`numeric(8,2)`) ·
`puesto_previo`. PK `(data_date, turno_id, puesto)`, UNIQUE
`(data_date, turno_id, dependencia_id)`.

### T12 — `audit.audit_event` (append-only, 60 meses)

`id` (seq) · `ts` · `actor` · `action` · `resource` · `result` · `ip`
(seudonimizada) · `user_agent` · `correlation_id` · `schema_version`.
`UNIQUE (id, ts)`; índice `(ts, actor, action)`.

### T13 — `app.webhook_registry` + `app.webhook_secret` (permanente)

- `webhook_registry`: `webhook_id` (text PK) · `doc_id` · `estado`
  (`activo`/`revocado`) · `revoked_at` · `created_at` · `last_seen_at`.
  Registra los orígenes (webhooks de Google Sheets) y su revocación individual.
- `webhook_secret`: `key_id` (text PK) · `webhook_id` (FK lógica) · `estado`
  (`vigente`/`rotada`/`revocada`) · `not_before` / `not_after` (ventana de
  solape de 24 h) · `created_at` · `rotated_at`. Guarda **solo metadata** del
  secreto versionado; **nunca** el material del secreto (vive en el secret
  manager del backend y en las `Script Properties` de Apps Script, §9.2).

### T14 — `app.role_capability` (configurable) + seeds

`role` (PK) · `capability` (PK) · `granted` (bool). Seeds = celdas «Sí» de §2.2.3
(11 filas); las «No» quedan implícitas (fail-closed).

---

### T74 — `app.consulta_event` (detalle de la hoja «CONSULTAS», 60 meses)

Sincroniza el modelo con la planilla oficial de la Jefatura: una fila por
consulta con las **20 columnas exactas** de la hoja `CONSULTAS` y los campos
técnicos de trazabilidad del evento de origen. Particionado mensual por
`fecha_consulta` (`RANGE`, retención 60 meses).

| Columna | Tipo | Regla |
|---------|------|-------|
| `fecha_consulta` | `date` | **Clave de partición**; requerida. |
| `hora_consulta` | `text` | Hora Consulta. |
| `turno` | `text` | Turno (MAÑANA/TARDE/NOCHE). |
| `jerarquia` | `text` | Jerarquía. |
| `personal_policial` | `text` | Personal Policial. |
| `jefatura_regional` | `text` | Jefatura Regional (agrupación del dashboard). |
| `dependencias` | `text` | Dependencias. |
| `tipo_consulta` | `text` | Tipo Consulta. |
| `identificacion` | `text` | Identificación. |
| `tipo_arma_vehiculo` | `text` | Tipo de Arma/Vehículo. |
| `resultado` | `text` | Resultado (agrupación de KPIs). |
| `causas_penales` | `text` | Causas Penales (agrupación de KPIs). |
| `registro_legajo` | `text` | Registro/Legajo. |
| `autoridad_judicial` | `text` | Autoridad Judicial. |
| `sistema_utilizado` | `text` | Sistema Utilizado. |
| `tramite_devuelto` | `text` | Trámite Devuelto. |
| `hora_resp` | `text` | Hora Resp. |
| `personal_que_informa` | `text` | Personal que Informa. |
| `cargo` | `text` | Cargo. |
| `operativos_preventivos` | `text` | Operativos Preventivos. |
| `event_id` / `doc_id` / `row_index` | `uuid` / `text` / `int` | Identidad técnica de la fila dentro del evento. |
| `seq` / `received_at` / `correlation_id` | `bigint` / `timestamptz` / `text` | Trazabilidad del evento aceptado. |

PK `(fecha_consulta, event_id, row_index)` (incluye la clave de partición, como
exige PostgreSQL). Índice único `(event_id, row_index, fecha_consulta)` para la
idempotencia del `INSERT ... ON CONFLICT DO NOTHING`. Índices de agrupación por
`turno`, `jefatura_regional`, `resultado` y `causas_penales`. El rol
`svc_dashboard` recibe `SELECT` (padre + particiones) vía
`app.refresh_svc_dashboard_grants()`, que junto con `app.roll_partitions()`
incluye esta tabla.

---

## 3. Rol `svc_dashboard` — permisos exactos (GRANT/REVOKE)

Definido en `0009_svc_dashboard` (función `app.refresh_svc_dashboard_grants()`).

**GRANT**

```sql
GRANT USAGE ON SCHEMA app TO svc_dashboard;
GRANT USAGE ON SCHEMA audit TO svc_dashboard;

GRANT SELECT ON app.snapshot_current TO svc_dashboard;
GRANT SELECT ON app.agg_hourly       TO svc_dashboard;   -- + particiones
GRANT SELECT ON app.agg_daily        TO svc_dashboard;   -- + particiones
GRANT SELECT ON app.ranking_snapshot TO svc_dashboard;   -- + particiones

GRANT SELECT (webhook_id, estado, created_at, last_seen_at, revoked_at)
    ON app.webhook_registry TO svc_dashboard;            -- limitado por columna

GRANT SELECT, INSERT ON audit.audit_event TO svc_dashboard;  -- + particiones
GRANT USAGE, SELECT ON SEQUENCE audit.audit_event_id_seq TO svc_dashboard;
```

**REVOKE (negación explícita)**

```sql
REVOKE ALL ON SCHEMA app FROM PUBLIC;
REVOKE ALL ON SCHEMA audit FROM PUBLIC;

REVOKE CREATE ON SCHEMA app   FROM svc_dashboard;   -- sin DDL
REVOKE CREATE ON SCHEMA audit FROM svc_dashboard;

REVOKE UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA app   FROM svc_dashboard;
REVOKE UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA audit FROM svc_dashboard;

REVOKE ALL ON app.ingest_event     FROM svc_dashboard;   -- tabla cruda cifrada
REVOKE ALL ON app.webhook_secret   FROM svc_dashboard;   -- metadata de secretos
REVOKE ALL ON app.role_capability  FROM svc_dashboard;
```

**Resultado neto:** `svc_dashboard` lee solo snapshot/agregados/ranking y
`webhook_registry` (columnas no sensibles), escribe solo `audit_event` (append),
y **no** puede: ejecutar DDL, `UPDATE`/`DELETE`/`TRUNCATE`, ni leer
`ingest_event` (cruda), `webhook_secret`, `role_capability` ni el material del
secreto del webhook.

> **Identidad de escritura:** la ingesta (verificación de firma HMAC, INSERT en
> `ingest_event`, UPSERT en `snapshot_current`, agregados) y la gestión de
> secretos de webhook (`platform.manage_webhook`) las realiza una identidad de
> servicio de escritura separada (fuera de alcance de F1/T15). `svc_dashboard`
> es la identidad de **lectura del dashboard + auditoría**.

---

## 4. Particionado por mes y cifrado de columna

**Particionado** (`PARTITION BY RANGE`, límites mensuales):

| Tabla | Columna de partición | Retención |
|-------|----------------------|-----------|
| `app.ingest_event` | `received_at` (`timestamptz`) | 90 días (3 meses) |
| `app.agg_hourly` | `bucket` (`timestamptz`) | 60 meses |
| `app.agg_daily` | `bucket` (`date`) | 60 meses |
| `app.ranking_snapshot` | `data_date` (`date`) | 60 meses |
| `audit.audit_event` | `ts` (`timestamptz`) | 60 meses |

- Particiones nombradas `<tabla>_YYYY_MM` (límites en UTC para `timestamptz`).
- Mantenimiento: `app.roll_partitions()` (crea mes actual + 2, elimina
  caducadas). Programar mensualmente (pg_cron o job del backend) y llamar
  `app.refresh_svc_dashboard_grants()` después (los privilegios del padre no se
  heredan a las hijas).
- Restricción de PostgreSQL: toda UNIQUE/PK sobre tabla particionada debe incluir
  la clave de partición → `UNIQUE (event_id, received_at)` y
  `UNIQUE (id, ts)`.

**Cifrado de columna** (`payload_ciphertext`, AES-256-GCM):

- El backend cifra **antes** de insertar; la columna solo contiene ciphertext.
- Clave de datos (DEK) envuelta por la KEK del **secret manager**; ni la KEK ni
  la DEK **viven en la BD** (RNF-02.a, §9.1–§9.2). `webhook_secret` guarda
  únicamente `key_id`, estado y fechas, nunca material de clave.
- `pgcrypto` (habilitada en `0001_base`) queda disponible como alternativa
  (`pgp_sym_encrypt`), pero el patrón recomendado es cifrar en el backend.

---

## 5. Coherencia de nombres con §7.9

| §7.9 (spec) | Tabla/columna implementada | Coincidencia |
|-------------|----------------------------|--------------|
| `ingest_event` — `event_id` UNIQUE, `payload_ciphertext`, `content_sha256` | `app.ingest_event` (90 d) | ✓ (`event_id` UNIQUE vía `(event_id, received_at)` por particionado) |
| `snapshot_current` — último payload por `doc_id`, base cold start | `app.snapshot_current` (1 fila/doc) | ✓ |
| `agg_hourly` / `agg_daily` — baselines «ayer», 60 meses | `app.agg_hourly` / `app.agg_daily` | ✓ |
| `ranking_snapshot` — `puesto_previo`, 60 meses | `app.ranking_snapshot` | ✓ |
| `audit_event` — append-only, 60 meses, sin UPDATE/DELETE | `audit.audit_event` | ✓ |
| `webhook_registry` — estado, documento asociado, revocación | `app.webhook_registry` | ✓ |
| `webhook_secret` — `key_id`, estado, fechas (solape 24 h) | `app.webhook_secret` | ✓ |
| `role_capability` — rol→capacidad configurable | `app.role_capability` | ✓ (tarea T14; §2.2.3) |

**Notas de decisión:**

- `webhook_id` es `text` en la BD (PK de `webhook_registry`); el ejemplo del
  sobre (§7.2 `"wh-sifcop-central"`) es literal. La cabecera `X-Webhook-Id` del
  wire mapea a este `webhook_id`.
- El **secreto del webhook** (`X-Webhook-Key-Id` → `webhook_secret.key_id`) se
  versiona con solape de **24 h**; la BD nunca contiene el material, solo
  metadata para rotación y revocación.
- `snapshot_current.payload` es `jsonb` **en claro** (agregado distribuible), no
  el cifrado: `payload_ciphertext` solo existe en `ingest_event`.
