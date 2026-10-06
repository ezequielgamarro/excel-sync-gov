"""F3: soporte de persistencia para ingesta/activación (T26/T27)

Revision ID: 0010_f3_ingest_support
Revises: 0009_svc_dashboard
Create Date: 2026-10-03

Añade, de forma idempotente, dos piezas que necesitan las tareas F3 (T26/T27)
sin tocar las tablas ya migradas:

1. ``app.ingest_event_seq`` — secuencia para asignar ``seq`` monótono a cada
   evento aceptado (orden canónico de aplicación, RNF-11.b). El ``seq`` lo
   asigna el backend (no el agente), igual que ``event_id`` lo genera la app.

2. ``app.agent_registry.agent_label`` — etiqueta legible del agente
   (p. ej. "Centro-01") aportada en el canje de activación (POST
   /agents/activate, T27). Opcional y sin datos sensibles.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0010_f3_ingest_support"
down_revision: Union[str, None] = "0009_svc_dashboard"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_SEQUENCE = """
CREATE SEQUENCE IF NOT EXISTS app.ingest_event_seq;
"""

_AGENT_REGISTRY = """
CREATE TABLE IF NOT EXISTS app.agent_registry (
    agent_id      uuid        PRIMARY KEY,
    agent_name    text        NOT NULL,
    registered_at timestamptz NOT NULL DEFAULT now()
);
"""

_AGENT_LABEL = """
ALTER TABLE app.agent_registry
    ADD COLUMN IF NOT EXISTS agent_label text;
"""

_COMMENTS = (
    "COMMENT ON SEQUENCE app.ingest_event_seq IS "
    "'Secuencia para asignar seq monótono a los eventos de ingesta (F3, RNF-11.b).'",
    "COMMENT ON COLUMN app.agent_registry.agent_label IS "
    "'Etiqueta legible del agente (p. ej. Centro-01), del canje de activación (T27).'",
)


def upgrade() -> None:
    op.execute(_SEQUENCE)
    op.execute(_AGENT_REGISTRY)
    op.execute(_AGENT_LABEL)
    for stmt in _COMMENTS:
        op.execute(stmt)


def downgrade() -> None:
    op.execute("ALTER TABLE app.agent_registry DROP COLUMN IF EXISTS agent_label")
    op.execute("DROP SEQUENCE IF EXISTS app.ingest_event_seq")
