# Migraciones (Alembic) — backend

Marco de migraciones del sistema **Google Sheets-to-Web** (Tarea T7, Fase F1). Gestiona el
esquema de PostgreSQL de forma versionada y reversible.

> **Zero Trust (spec §9.5, RNF-13):** la URL de conexión **nunca** está en un
> fichero. `env.py` lee `DATABASE_URL` del entorno en tiempo de ejecución; las
> credenciales se inyectan desde el gestor de secretos.

## Estructura

```
backend/
├── alembic.ini                 # configuración de Alembic (URL vacía a propósito)
└── alembic/
    ├── env.py                  # lee DATABASE_URL y ejecuta migraciones (asyncpg)
    ├── script.py.mako          # plantilla de nuevas revisiones
    ├── README.md               # este fichero
    └── versions/
        ├── 0001_base.py                # T7: extensiones + esquemas + uuidv7() (sin tablas)
        ├── 0002_ingest_event.py        # T8: app.ingest_event (particionado, 90 d)
        ├── 0003_snapshot_current.py    # T9: app.snapshot_current (cold start)
        ├── 0004_agg_hourly_daily.py    # T10: app.agg_hourly + app.agg_daily
        ├── 0005_ranking_snapshot.py    # T11: app.ranking_snapshot (Top 5)
        ├── 0006_audit_event.py         # T12: audit.audit_event (append-only)
        ├── 0007_agent_registry_keyring.py  # T13: origen (webhook_registry + webhook_secret)
        ├── 0008_role_capability.py     # T14: role_capability + seeds (§2.2.3)
        └── 0009_svc_dashboard.py       # T15: rol svc_dashboard + particionado + cifrado
```

El diagrama ER textual de las 8 tablas y sus relaciones está en
[`backend/docs/schema.md`](../docs/schema.md).

## Requisitos e instalación

Las dependencias se declaran en el `pyproject.toml` raíz, grupo `backend`:

- `alembic` — framework de migraciones.
- `asyncpg` — driver asíncrono (coincide con `DATABASE_URL=postgresql+asyncpg://`).
- `psycopg[binary]` — driver síncrono alternativo (opcional).

```bash
# con uv
uv sync --group backend

# o con pip
pip install alembic asyncpg "psycopg[binary]"
```

## Variable de entorno

Define `DATABASE_URL` (ver `backend/.env.example`):

```bash
export DATABASE_URL="postgresql+asyncpg://svc_dashboard:<contraseña>@<host>:5432/<db>?sslmode=verify-full"
```

`env.py` **falla cerrado** (raise) si `DATABASE_URL` no está definida.

## Comandos

Ejecutar siempre desde `backend/` (Alembic localiza `alembic.ini` por directorio):

```bash
cd backend

alembic upgrade head           # aplicar todas las migraciones (forward)
alembic upgrade <revision>     # avanzar hasta una revisión concreta
alembic downgrade -1           # revertir la última revisión
alembic downgrade base         # revertir todo hasta la base (0001_base)
alembic current                # revisión actual de la BD
alembic history                # historial de revisiones
alembic upgrade head --sql     # emitir el SQL sin conectar (modo offline)
```

## Convención de naming de revisiones

- `revision` = ID **secuencial, corto y descriptivo**: `0001_base`, `0002_ingest_event`,
  `0003_snapshot_current`, … (una revisión por tarea de la fase F1, T7→T15).
- `down_revision` enlaza la revisión anterior formando una cadena lineal (sin
  branches para este sistema).
- Los ficheros de `versions/` se escriben **a mano** (no autogenerate). La
  plantilla `script.py.mako` deja `upgrade()`/`downgrade()` con `pass` para rellenar.

## Estrategia UUIDv7

PostgreSQL **no** genera UUIDv7 de forma nativa hasta la **v18**. Decisión adoptada:

1. **Fuente autoritativa:** la app genera `event_id` con la librería Python
   `uuid6`/`uuid7` (UUIDv7 RFC 9562) y lo envía en el sobre cifrado (§7.2). La
   columna se define como `UUID` nativo en `ingest_event` (T8).
2. **Fallback SQL:** `app.uuidv7()` (creada en `0001_base`) genera UUIDv7 válidos
   a partir de `clock_timestamp()` + `gen_random_bytes(10)` de `pgcrypto`, para
   defaults o generación puntual en BD.
3. **`uuid-ossp` se habilita** (`CREATE EXTENSION IF NOT EXISTS`) por
   compatibilidad del stack y utilidades de generación de UUID, pero **no**
   implementa UUIDv7; la estrategia v7 la aporta `app.uuidv7()`.

## Extensiones habilitadas

| Extensión | Uso | Habilitada en |
|-----------|-----|---------------|
| `pgcrypto` | Cifrado de columna (`payload_ciphertext` AES-256-GCM, §2.2.4) y `gen_random_bytes` para `uuidv7()`. | `0001_base` |
| `uuid-ossp` | Utilidades de generación de UUID (`uuid_generate_v*`); no aporta UUIDv7. Se habilita por compatibilidad del stack. | `0001_base` |

## Esquemas / namespaces

La spec no fija nombres de esquema; se adoptan dos por **mínimo privilegio**
(§2.2.4 / §2.2.6), creados en `0001_base`:

| Esquema | Contenido | Motivación |
|---------|-----------|------------|
| `app` | `ingest_event`, `snapshot_current`, `agg_hourly`, `agg_daily`, `ranking_snapshot`, `webhook_registry`, `webhook_secret`, `role_capability` | Datos operativos. |
| `audit` | `audit_event` | Aislar la bitácora append-only para que `svc_dashboard` tenga solo `INSERT`+`SELECT` (sin `UPDATE`/`DELETE`). |

**Convención para T8–T14:** prefijar las tablas con su esquema (`app.ingest_event`,
`audit.audit_event`, etc.) y referenciar columnas UUID con tipo `UUID` nativo.

## Idempotencia (contrato up/down)

Toda migración debe poder ejecutarse varias veces sin efectos secundarios:

- **up**: `CREATE ... IF NOT EXISTS`, `CREATE OR REPLACE FUNCTION`.
- **down**: `DROP ... IF EXISTS`; los esquemas se dropean **sin `CASCADE`** (falla
  si no están vacíos → fail-closed). Al ejecutar `alembic downgrade base` las
  migraciones posteriores ya se revierten en orden inverso antes de llegar a la base.

## Rol `svc_dashboard` y particionado (T15)

La revisión `0009_svc_dashboard` crea la identidad de servicio de mínimo
privilegio y las utilidades de particionado:

- **Rol `svc_dashboard`** (`LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE`):
  `SELECT` sobre `snapshot_current`/`agg_*`/`ranking_snapshot`, `SELECT` limitado
  por columna sobre `webhook_registry` (sin `webhook_secret`) e
  `INSERT`+`SELECT` sobre `audit.audit_event`. **Sin** DDL ni `UPDATE`/`DELETE`.
  La contraseña se inyecta desde el secret manager (nunca en una migración).
- **Particionado por mes** (`RANGE`): `ingest_event`, `agg_hourly`, `agg_daily`,
  `ranking_snapshot`, `audit_event`. `app.roll_partitions()` crea particiones
  futuras y aplica retención (§7.9); programarla mensualmente (pg_cron o job del
  backend) y llamar después a `app.refresh_svc_dashboard_grants()` para propagar
  privilegios a las particiones nuevas (PostgreSQL no hereda los privilegios del
  padre a las hijas).

## Notas

- Las migraciones están listas para correr cuando exista una base de datos de
  desarrollo; **no se ejecutan contra un servidor real en F1**.
- Particionado: toda restricción UNIQUE/PK sobre tabla particionada debe incluir
  la clave de partición. Por eso `event_id` en `ingest_event` es
  `UNIQUE (event_id, received_at)` (ver docstring de `0002`), y `audit_event.id`
  es `UNIQUE (id, ts)`.
