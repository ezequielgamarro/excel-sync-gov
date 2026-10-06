"""ingest_event: cabecera de cada evento ingerido (T8)

Revision ID: 0002_ingest_event
Revises: 0001_base
Create Date: 2026-10-03

T8 (Fase F1) — tabla ``app.ingest_event``, cabecera inmutable de cada evento
aceptado por el backend. Es el registro fuente de la cadena de confianza:
clave de idempotencia ``event_id`` (UUIDv7 generado en la app), blob cifrado
``payload_ciphertext`` (AES-256-GCM) y retención de 90 días con particionado
mensual por ``received_at``.

Decisiones de diseño (spec §7.9, §2.2.4, RNF-02.a, RNF-11.a):

- ``event_id`` es UUIDv7 y lo genera la **app** (ver README «Estrategia
  UUIDv7»); aquí la columna es ``UUID`` nativo, sin default SQL.
- **Particionado por ``RANGE (received_at)``.** PostgreSQL exige que toda
  restricción UNIQUE/PK sobre una tabla particionada incluya la clave de
  partición. Por eso la unicidad de ``event_id`` se materializa como
  ``UNIQUE (event_id, received_at)``. Como ``event_id`` es UUIDv7 (timestamp
  ordenado) y ``received_at`` es el instante de aceptación, un mismo
  ``event_id`` cae siempre en la misma partición → la garantía es, en la
  práctica, global. La idempotencia real la aplica el backend en T26 con
  ``INSERT ... ON CONFLICT (event_id, received_at) DO NOTHING``.
- ``payload_ciphertext`` es ``bytea``: el backend cifra AES-256-GCM **antes**
  de insertar; la clave vive en el secret manager, **nunca** en la BD
  (RNF-02.a). Esta columna jamás recibe texto claro.
- Retención 90 días: particiones mensuales + ``app.roll_partitions()`` (T15),
  que elimina particiones viejas y crea las siguientes.

Idempotente: up con ``IF NOT EXISTS`` / ``OR REPLACE``; down con ``IF EXISTS``
y ``CASCADE`` (necesario para soltar las particiones hijas).
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0002_ingest_event"
down_revision: Union[str, None] = "0001_base"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# =============================================================================
# SQL reutilizable
# =============================================================================

# Crea (idempotente) la partición mensual ``<tabla>_YYYY_MM`` para una tabla
# particionada por RANGE. Soporta columnas de partición ``timestamptz`` y
# ``date`` (p_coltype). Los límites mensuales se calculan en UTC para el caso
# timestamptz (evita ambigüedad de timezone de sesión).
_CREATE_MONTH_PARTITION = """
CREATE OR REPLACE FUNCTION app.create_month_partition(
    p_schema  text,
    p_table   text,
    p_month   date,
    p_coltype text DEFAULT 'timestamptz'
) RETURNS text
LANGUAGE plpgsql
VOLATILE
AS $$
DECLARE
    part_name  text;
    start_ts   timestamptz;
    end_ts     timestamptz;
    start_date date;
    end_date   date;
    sql_stmt   text;
BEGIN
    part_name := p_table || '_' || to_char(p_month, 'YYYY_MM');

    IF to_regclass(format('%I.%I', p_schema, part_name)) IS NOT NULL THEN
        RETURN part_name;  -- ya existe: idempotente
    END IF;

    IF p_coltype = 'date' THEN
        start_date := p_month;
        end_date   := (p_month + interval '1 month')::date;
        sql_stmt := format(
            'CREATE TABLE %I.%I PARTITION OF %I.%I FOR VALUES FROM (%L) TO (%L)',
            p_schema, part_name, p_schema, p_table, start_date, end_date
        );
    ELSE
        start_ts := (to_char(p_month, 'YYYY-MM') || '-01 00:00:00+00')::timestamptz;
        end_ts   := (to_char((p_month + interval '1 month')::date, 'YYYY-MM')
                     || '-01 00:00:00+00')::timestamptz;
        sql_stmt := format(
            'CREATE TABLE %I.%I PARTITION OF %I.%I FOR VALUES FROM (%L) TO (%L)',
            p_schema, part_name, p_schema, p_table, start_ts, end_ts
        );
    END IF;

    EXECUTE sql_stmt;
    RETURN part_name;
END;
$$;
"""

# Crea un rango continuo de particiones mensuales [p_first, p_last].
_CREATE_MONTH_PARTITIONS = """
CREATE OR REPLACE FUNCTION app.create_month_partitions(
    p_schema  text,
    p_table   text,
    p_coltype text,
    p_first   date,
    p_last    date
) RETURNS void
LANGUAGE plpgsql
VOLATILE
AS $$
DECLARE
    m date := p_first;
BEGIN
    WHILE m <= p_last LOOP
        PERFORM app.create_month_partition(p_schema, p_table, m, p_coltype);
        m := (m + interval '1 month')::date;
    END LOOP;
END;
$$;
"""

# Tabla padre (particionada) + restricción de formato del hash SHA-256 (64 hex).
_INGEST_EVENT = """
CREATE TABLE IF NOT EXISTS app.ingest_event (
    event_id           uuid        NOT NULL,
    doc_id             text        NOT NULL,
    webhook_id         uuid        NOT NULL,
    content_sha256     text        NOT NULL,
    payload_ciphertext bytea       NOT NULL,
    seq                bigint      NOT NULL,
    received_at        timestamptz NOT NULL DEFAULT now(),
    correlation_id     text,
    CONSTRAINT chk_ingest_event_sha256
        CHECK (content_sha256 ~ '^[0-9a-f]{64}$')
) PARTITION BY RANGE (received_at);
"""

# Particiones iniciales: mes actual + 2 meses siguientes (ventana de escritura).
_INITIAL_PARTITIONS = """
SELECT app.create_month_partitions(
    'app', 'ingest_event', 'timestamptz',
    date_trunc('month', now())::date,
    (date_trunc('month', now()) + interval '2 months')::date
);
"""

_INDEXES = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_ingest_event_event_id "
    "ON app.ingest_event (event_id, received_at)",
    "CREATE INDEX IF NOT EXISTS ix_ingest_event_webhook_received "
    "ON app.ingest_event (webhook_id, received_at)",
    "CREATE INDEX IF NOT EXISTS ix_ingest_event_correlation ON app.ingest_event (correlation_id)",
)

_COMMENTS = (
    "COMMENT ON TABLE app.ingest_event IS "
    "'Cabecera inmutable de cada evento ingerido (T8, spec §7.9). "
    "Retención 90 días, particionado mensual por received_at.'",
    "COMMENT ON COLUMN app.ingest_event.event_id IS "
    "'UUIDv7 único (clave de idempotencia); generado en la app, no en la BD.'",
    "COMMENT ON COLUMN app.ingest_event.doc_id IS "
    "'Documento Excel declarado de origen (p. ej. sifcop-resumen).'",
    "COMMENT ON COLUMN app.ingest_event.webhook_id IS "
    "'UUID del origen webhook emisor (FK lógica a app.webhook_registry.webhook_id, llega en T13).'",
    "COMMENT ON COLUMN app.ingest_event.content_sha256 IS "
    "'SHA-256 (64 hex minúsculas) del contenido normalizado del documento.'",
    "COMMENT ON COLUMN app.ingest_event.payload_ciphertext IS "
    "'Blob cifrado AES-256-GCM (bytea). La clave vive en el secret manager, "
    "NUNCA en la BD (RNF-02.a). Jamás contiene texto claro.'",
    "COMMENT ON COLUMN app.ingest_event.seq IS "
    "'Secuencia monótona asignada por el backend (orden canónico de aplicación).'",
    "COMMENT ON COLUMN app.ingest_event.correlation_id IS "
    "'Identificador de correlación extremo a extremo (trazas, RNF-07.b).'",
)


def upgrade() -> None:
    # 1. Utilidades de particionado (reutilizadas por T10/T11/T12/T15).
    op.execute(_CREATE_MONTH_PARTITION)
    op.execute(_CREATE_MONTH_PARTITIONS)

    # 2. Tabla padre particionada.
    op.execute(_INGEST_EVENT)

    # 3. Particiones iniciales (mes actual + 2 meses).
    op.execute(_INITIAL_PARTITIONS)

    # 4. Índices (se propagan automáticamente a las particiones).
    # asyncpg no admite múltiples comandos en un prepared statement: cada
    # sentencia se envía por separado.
    for stmt in _INDEXES:
        op.execute(stmt)

    # 5. Documentación de columnas.
    for stmt in _COMMENTS:
        op.execute(stmt)


def downgrade() -> None:
    # CASCADE suelta la tabla padre junto con sus particiones e índices.
    op.execute("DROP TABLE IF EXISTS app.ingest_event CASCADE")

    # Utilidades de particionado (orden inverso: primero la que depende).
    op.execute("DROP FUNCTION IF EXISTS app.create_month_partitions(text, text, text, date, date)")
    op.execute("DROP FUNCTION IF EXISTS app.create_month_partition(text, text, date, text)")
