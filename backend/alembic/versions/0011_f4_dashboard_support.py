"""F4: soporte de cold start — ``agent_id`` en snapshot_current (T30)

Revision ID: 0011_f4_dashboard_support
Revises: 0010_f3_ingest_support
Create Date: 2026-10-03

El sobre ``indicators.snapshot`` del cold start (``GET /dashboard/snapshot``,
T30) debe incluir ``source.agent_id`` (§7.2, JSON Schema ``SnapshotMessage``).
Ese dato no vive en el documento descifrado del agente (el ``agent_id`` viaja en
el AAD del sobre, §9.2), por lo que se persiste de forma explícita en
``app.snapshot_current`` al aceptar la instantánea (F3/T26 actualiza el UPSERT).

Idempotente: ``ADD COLUMN IF NOT EXISTS``. La columna es ``uuid`` y **nullable**
(las filas previas a esta migración no tienen agente conocido); el cold start
emitirá ``""`` en ese caso.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0011_f4_dashboard_support"
down_revision: Union[str, None] = "0010_f3_ingest_support"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ADD_AGENT_ID = """
ALTER TABLE app.snapshot_current
    ADD COLUMN IF NOT EXISTS agent_id uuid;
"""

_COMMENT = """
COMMENT ON COLUMN app.snapshot_current.agent_id IS
    'Agente que publicó la última instantánea (source.agent_id del cold start, F4/T30). '
    'Nullable: las filas previas a la migración 0011 no tienen agente conocido.';
"""


def upgrade() -> None:
    op.execute(_ADD_AGENT_ID)
    op.execute(_COMMENT)


def downgrade() -> None:
    op.execute("ALTER TABLE app.snapshot_current DROP COLUMN IF EXISTS agent_id")
