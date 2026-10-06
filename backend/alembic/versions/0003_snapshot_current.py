"""snapshot_current: última instantánea aceptada por doc_id (T9)

Revision ID: 0003_snapshot_current
Revises: 0002_ingest_event
Create Date: 2026-10-03

T9 (Fase F1) — tabla ``app.snapshot_current``: una fila por ``doc_id`` con la
última instantánea aceptada. Es la base del **cold start** (RNF-06.e, T30) y
la fuente para recomponer estado sin depender de Redis.

Decisiones de diseño (spec §7.9, §7.7):

- ``doc_id`` es la PK (1 fila por documento; sistema unidireccional, una sala
  = una instancia → normalmente una única fila). La escritura es un UPSERT
  (T26): se sobrescribe con la instantánea más reciente.
- ``payload`` es ``jsonb`` **en claro** (la instantánea ya descifrada y
  validada por el backend). Es el agregado distribuible, no el blob cifrado:
  ``payload_ciphertext`` vive únicamente en ``ingest_event``. El mínimo
  privilegio de ``svc_dashboard`` (T15) permite SELECT aquí porque es la vía
  de lectura del dashboard (a diferencia de ``ingest_event``, tabla cruda).
- ``event_id`` es **FK lógica** a ``app.ingest_event.event_id``: no se
  materializa una FOREIGN KEY porque (a) la tabla de referencia está
  particionada y PostgreSQL no soporta FK hacia tablas particionadas, y (b) la
  fila actual es un puntero al último evento, no una relación de integridad.
  La **identidad del origen** (pivote Apps Script + HMAC) se resuelve a través
  de esa fila: ``app.ingest_event.webhook_id`` → ``app.webhook_registry``
  (FK lógica, llega en T13); no se duplica en esta tabla.
- ``data_date`` es el día de datos del acumulado (clave para «vs ayer»).

Idempotente: up con ``IF NOT EXISTS``; down con ``IF EXISTS``.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0003_snapshot_current"
down_revision: Union[str, None] = "0002_ingest_event"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SNAPSHOT_CURRENT = """
CREATE TABLE IF NOT EXISTS app.snapshot_current (
    doc_id     text        PRIMARY KEY,
    event_id   uuid        NOT NULL,
    payload    jsonb       NOT NULL,
    data_date  date        NOT NULL,
    seq        bigint      NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now()
);
"""

_INDEXES = """
CREATE INDEX IF NOT EXISTS ix_snapshot_current_event_id
    ON app.snapshot_current (event_id);
"""

_COMMENTS = (
    "COMMENT ON TABLE app.snapshot_current IS "
    "'Última instantánea aceptada por doc_id (1 fila/doc, T9, spec §7.9). "
    "Base del cold start.'",
    "COMMENT ON COLUMN app.snapshot_current.doc_id IS "
    "'Clave primaria: documento Excel declarado (p. ej. sifcop-resumen).'",
    "COMMENT ON COLUMN app.snapshot_current.event_id IS "
    "'FK lógica al último app.ingest_event.event_id aceptado (sin FK física).'",
    "COMMENT ON COLUMN app.snapshot_current.payload IS "
    "'Payload completo descifrado y validado (jsonb, en claro). Agregado "
    "distribuible, no cifrado.'",
    "COMMENT ON COLUMN app.snapshot_current.data_date IS "
    "'Día de datos (YYYY-MM-DD) del acumulado, clave para la comparación vs ayer.'",
    "COMMENT ON COLUMN app.snapshot_current.seq IS "
    "'Secuencia monótona del último evento aplicado (orden canónico).'",
)


def upgrade() -> None:
    op.execute(_SNAPSHOT_CURRENT)
    op.execute(_INDEXES)
    for stmt in _COMMENTS:
        op.execute(stmt)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS app.snapshot_current")
