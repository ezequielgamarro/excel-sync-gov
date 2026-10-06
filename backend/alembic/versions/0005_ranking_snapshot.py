"""ranking_snapshot: Top 5 por día/turno (histórico de ranking) (T11)

Revision ID: 0005_ranking_snapshot
Revises: 0004_agg_hourly_daily
Create Date: 2026-10-03

T11 (Fase F1) — tabla ``app.ranking_snapshot``: histórico del ranking de
dependencias Top 5 (VIS-07) por día y turno. Conserva el puesto actual y el
``puesto_previo`` para habilitar el destello de cambio de posición (RF-04.g) y
la auditoría de «quién vio un reordenamiento».

Modelo (spec §7.6, §7.9):

- Clave natural ``(data_date, turno_id, puesto)``: hasta 5 filas por día/turno,
  ordenadas por intervenciones descendente (desempate alfabético).
- ``puesto_previo`` registra el puesto en la instantánea anterior (comparación
  histórica); NULL si no hay dato previo.
- ``variacion_abs`` / ``variacion_pct`` se almacenan **fotografiados** en el
  momento del snapshot (a diferencia de ``agg_*``, que los deriva en lectura):
  el ranking histórico necesita la variación tal y como se mostró.
- ``variacion_pct`` es ``numeric(8,2)`` (porcentaje con 2 decimales, RNF-15.b).

Particionado y retención (spec §7.9): 60 meses, ``PARTITION BY RANGE`` mensual
sobre ``data_date`` (tipo ``date``). Reutiliza ``app.create_month_partitions``.

Idempotente: up con ``IF NOT EXISTS``; down con ``IF EXISTS`` + ``CASCADE``.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0005_ranking_snapshot"
down_revision: Union[str, None] = "0004_agg_hourly_daily"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_RANKING_SNAPSHOT = """
CREATE TABLE IF NOT EXISTS app.ranking_snapshot (
    data_date      date         NOT NULL,
    turno_id       text         NOT NULL,
    puesto         integer      NOT NULL,
    dependencia_id text         NOT NULL,
    comisaria      text         NOT NULL,
    intervenciones bigint       NOT NULL,
    variacion_abs  bigint,
    variacion_pct  numeric(8,2),
    puesto_previo  integer,
    CONSTRAINT pk_ranking_snapshot PRIMARY KEY (data_date, turno_id, puesto),
    CONSTRAINT uq_ranking_snapshot_dep UNIQUE (data_date, turno_id, dependencia_id),
    CONSTRAINT chk_ranking_snapshot_puesto CHECK (puesto BETWEEN 1 AND 5),
    CONSTRAINT chk_ranking_snapshot_interv CHECK (intervenciones >= 0)
) PARTITION BY RANGE (data_date);
"""

_INITIAL_PARTITIONS = """
SELECT app.create_month_partitions(
    'app', 'ranking_snapshot', 'date',
    date_trunc('month', now())::date,
    (date_trunc('month', now()) + interval '2 months')::date
);
"""

_INDEXES = """
CREATE INDEX IF NOT EXISTS ix_ranking_snapshot_dependencia
    ON app.ranking_snapshot (dependencia_id, data_date);
"""

_COMMENTS = (
    "COMMENT ON TABLE app.ranking_snapshot IS "
    "'Top 5 por día/turno (histórico de ranking, T11, spec §7.9). Retención "
    "60 meses, particionado mensual.'",
    "COMMENT ON COLUMN app.ranking_snapshot.puesto IS "
    "'Posición en el ranking (1..5).'",
    "COMMENT ON COLUMN app.ranking_snapshot.puesto_previo IS "
    "'Puesto en la instantánea anterior (habilita el destello de cambio, "
    "RF-04.g); NULL si no hay dato previo.'",
    "COMMENT ON COLUMN app.ranking_snapshot.variacion_pct IS "
    "'Variación porcentual fotografiada en el momento del snapshot (2 decimales).'",
)


def upgrade() -> None:
    op.execute(_RANKING_SNAPSHOT)
    op.execute(_INITIAL_PARTITIONS)
    op.execute(_INDEXES)
    for stmt in _COMMENTS:
        op.execute(stmt)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS app.ranking_snapshot CASCADE")
