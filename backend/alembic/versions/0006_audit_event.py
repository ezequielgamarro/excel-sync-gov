"""audit_event: bitácora append-only (T12)

Revision ID: 0006_audit_event
Revises: 0005_ranking_snapshot
Create Date: 2026-10-03

T12 (Fase F1) — tabla ``audit.audit_event``: bitácora **append-only** de toda
acción sensible (RNF-08). Vive en el esquema ``audit`` para aislar el mínimo
privilegio: el rol de servicio ``svc_dashboard`` (T15) recibe únicamente
``INSERT`` + ``SELECT``, **sin** ``UPDATE``/``DELETE``/``TRUNCATE``.

Modelo (spec §7.9, RNF-08.b):

- ``id``: ``bigint`` alimentado por la secuencia ``audit.audit_event_id_seq``
  (equivalente a ``bigserial``). Se crea la secuencia de forma explícita para
  evitar las restricciones de ``serial`` sobre tablas particionadas y para
  poder otorgar ``USAGE`` a ``svc_dashboard`` en T15.
- La PK/unicidad sobre tabla particionada debe incluir la clave de partición
  (``ts``); por eso la unicidad del ``id`` se materializa como
  ``UNIQUE (id, ts)`` (con ``id`` generado por secuencia compartida, el ``id``
  es único globalmente).
- ``actor`` es la identidad del emisor en texto: el ``sub`` del operador
  autenticado con JWT nativo o el ``webhook_id`` del origen Google Sheets
  (RNF-08.b). ``action`` nombra la
  acción sensible de cualquiera de esos orígenes; no hay columnas específicas
  del diseño antiguo.
- ``ip`` está **seudonimizada** (hash/trunc; nunca la IP completa ni PII,
  RNF-08.c).
- Índice ``(ts, actor, action)`` para las consultas de auditoría por rango de
  tiempo y actor (T32, capacidad ``audit.view``).

Append-only: además del GRANT/REVOKE de mínimo privilegio (T15, migración
``0009``), la tabla se blinda con un trigger ``BEFORE UPDATE OR DELETE`` que
**rechaza** toda mutación de filas, independientemente del rol. La retención de
**60 meses** se aplica por eliminación de particiones caducadas
(``app.roll_partitions()``, T15), nunca por ``DELETE`` de filas.

Particionado y retención (spec §7.9): 60 meses, ``PARTITION BY RANGE`` mensual
sobre ``ts``. Reutiliza ``app.create_month_partition``.

Idempotente: up con ``IF NOT EXISTS`` / ``OR REPLACE``; down con ``IF EXISTS``
+ ``CASCADE``.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0006_audit_event"
down_revision: Union[str, None] = "0005_ranking_snapshot"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SEQUENCE = """
CREATE SEQUENCE IF NOT EXISTS audit.audit_event_id_seq;
"""

_AUDIT_EVENT = """
CREATE TABLE IF NOT EXISTS audit.audit_event (
    id             bigint      NOT NULL DEFAULT nextval('audit.audit_event_id_seq'),
    ts             timestamptz NOT NULL DEFAULT now(),
    actor          text        NOT NULL,
    action         text        NOT NULL,
    resource       text        NOT NULL,
    result         text        NOT NULL,
    ip             text,
    user_agent     text,
    correlation_id text,
    schema_version text
) PARTITION BY RANGE (ts);
"""

_INITIAL_PARTITIONS = """
SELECT app.create_month_partitions(
    'audit', 'audit_event', 'timestamptz',
    date_trunc('month', now())::date,
    (date_trunc('month', now()) + interval '2 months')::date
);
"""

_INDEXES = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_audit_event_id ON audit.audit_event (id, ts)",
    "CREATE INDEX IF NOT EXISTS ix_audit_event_ts_actor_action ON audit.audit_event (ts, actor, action)",
    "CREATE INDEX IF NOT EXISTS ix_audit_event_correlation ON audit.audit_event (correlation_id)",
)

# Blindaje append-only a nivel de fila: rechaza UPDATE/DELETE sea cual sea el
# rol, como defensa en profundidad sobre el GRANT/REVOKE de svc_dashboard (T15).
# El trigger se propaga a las particiones (PostgreSQL 13+). La retención de 60
# meses se ejecuta por DROP de particiones, que NO dispara triggers de fila.
_APPEND_ONLY = (
    """CREATE OR REPLACE FUNCTION audit.audit_event_forbid_mutation()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION
        'audit.audit_event es append-only: UPDATE/DELETE prohibido (RNF-08.d)';
END;
$$""",
    "DROP TRIGGER IF EXISTS trg_audit_event_immutable ON audit.audit_event",
    """CREATE TRIGGER trg_audit_event_immutable
    BEFORE UPDATE OR DELETE ON audit.audit_event
    FOR EACH ROW EXECUTE FUNCTION audit.audit_event_forbid_mutation()""",
)

# Negación explícita para el rol de servicio, si ya existiera: sin UPDATE ni
# DELETE ni TRUNCATE sobre la bitácora (idempotente: REVOKE es no-op si el
# privilegio o el rol no existen). El rol se crea en T15 (0009).
_REVOKE_SERVICE = """
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'svc_dashboard') THEN
        EXECUTE 'REVOKE UPDATE, DELETE, TRUNCATE '
             || 'ON audit.audit_event FROM svc_dashboard';
    END IF;
END
$$;
"""

_COMMENTS = (
    "COMMENT ON TABLE audit.audit_event IS "
    "'Bitácora append-only de acciones sensibles (T12, RNF-08). Retención "
    "60 meses, particionado mensual. Trigger + GRANT/REVOKE bloquean "
    "UPDATE/DELETE desde cualquier rol.'",
    "COMMENT ON COLUMN audit.audit_event.actor IS "
    "'Actor de la acción: sub del operador autenticado (JWT nativo) o webhook_id "
    "del origen Google Sheets (RNF-08.b).'",
    "COMMENT ON COLUMN audit.audit_event.ip IS "
    "'IP seudonimizada (hash/trunc); nunca IP completa ni PII (RNF-08.c).'",
    "COMMENT ON COLUMN audit.audit_event.schema_version IS "
    "'Versión semver del esquema de mensaje relacionado (§7.8).'",
)


def upgrade() -> None:
    op.execute(_SEQUENCE)
    op.execute(_AUDIT_EVENT)
    op.execute(_INITIAL_PARTITIONS)
    for stmt in _INDEXES:
        op.execute(stmt)
    for stmt in _APPEND_ONLY:
        op.execute(stmt)
    op.execute(_REVOKE_SERVICE)
    for stmt in _COMMENTS:
        op.execute(stmt)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS audit.audit_event CASCADE")
    op.execute("DROP FUNCTION IF EXISTS audit.audit_event_forbid_mutation()")
    op.execute("DROP SEQUENCE IF EXISTS audit.audit_event_id_seq")
