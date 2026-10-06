"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

Convenciones del proyecto (ver backend/alembic/README.md):

- ``revision`` = ID corto y descriptivo, secuencial (p. ej. ``0002_ingest_event``);
  la migración base es ``0001_base`` (T7).
- Las migraciones se escriben A MANO (no autogenerate) y deben ser IDEMPOTENTES:
  up con ``IF NOT EXISTS`` / ``OR REPLACE``; down con ``IF EXISTS``.
- Tablas por esquema: ``app`` (operativo) y ``audit`` (append-only), según T7.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

# Identificadores de revisión, usados por Alembic.
revision: str = ${repr(up_revision)}
down_revision: Union[str, None] = ${repr(down_revision)}
branch_labels: Union[str, Sequence[str], None] = ${repr(branch_labels)}
depends_on: Union[str, Sequence[str], None] = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
