"""agg_hourly + agg_daily: agregados por hora/día (T10)

Revision ID: 0004_agg_hourly_daily
Revises: 0003_snapshot_current
Create Date: 2026-10-03

T10 (Fase F1) — tablas ``app.agg_hourly`` y ``app.agg_daily``: series
agregadas por dimensión temporal (hora/día), unidad regional, turno operativo
y KPI. ``agg_daily`` alimenta los ``baseline_value`` de «vs ayer»; ``agg_hourly``
alimenta el histórico de tendencia (T31/T33).

Modelo (spec §7.3–§7.6, §7.9):

- Una fila está alcanceada por ``(bucket, kpi_id, unidad_id, turno_id)``. Las
  dimensiones son **mutuamente excluyentes** por fila y se representan con
  sentinela ``''`` (cadena vacía) cuando no aplican, para mantener la PK válida
  (NULL no está permitido en una PK) y portable a cualquier versión de
  PostgreSQL:
    · KPI total (VIS-01..04): ``kpi_id`` = clave canónica, ``unidad_id=''``,
      ``turno_id=''``.
    · Regional (VIS-05): ``kpi_id='intervenciones'``, ``unidad_id`` ∈ catálogo
      de 5, ``turno_id=''``.
    · Turnos (VIS-06): ``kpi_id='intervenciones'``, ``turno_id`` ∈
      {MAÑANA, TARDE, NOCHE}, ``unidad_id=''``.
- ``value`` es el acumulado (entero no negativo). ``baseline_value`` es el
  acumulado del periodo de referencia (ayer mismo tramo / mismo turno); NULL
  cuando no hay referencia (``has_reference=false``).
- ``delta_abs``/``delta_pct``/``direction`` se calculan en lectura (T33), no se
  almacenan (evita divergencias; fuente única de verdad §7.1).

Particionado y retención (spec §7.9): 60 meses, ``PARTITION BY RANGE`` mensual.
``agg_hourly`` particiona por ``bucket timestamptz`` (inicio de hora, UTC);
``agg_daily`` por ``bucket date`` (día). Reutiliza ``app.create_month_partition``
de ``0002_ingest_event``.

Idempotente: up con ``IF NOT EXISTS``; down con ``IF EXISTS`` + ``CASCADE``.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0004_agg_hourly_daily"
down_revision: Union[str, None] = "0003_snapshot_current"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_AGG_HOURLY = """
CREATE TABLE IF NOT EXISTS app.agg_hourly (
    bucket         timestamptz NOT NULL,
    kpi_id         text        NOT NULL,
    unidad_id      text        NOT NULL DEFAULT '',
    turno_id       text        NOT NULL DEFAULT '',
    value          bigint      NOT NULL,
    baseline_value bigint,
    CONSTRAINT pk_agg_hourly PRIMARY KEY (bucket, kpi_id, unidad_id, turno_id),
    CONSTRAINT chk_agg_hourly_value CHECK (value >= 0)
) PARTITION BY RANGE (bucket);
"""

_AGG_DAILY = """
CREATE TABLE IF NOT EXISTS app.agg_daily (
    bucket         date        NOT NULL,
    kpi_id         text        NOT NULL,
    unidad_id      text        NOT NULL DEFAULT '',
    turno_id       text        NOT NULL DEFAULT '',
    value          bigint      NOT NULL,
    baseline_value bigint,
    CONSTRAINT pk_agg_daily PRIMARY KEY (bucket, kpi_id, unidad_id, turno_id),
    CONSTRAINT chk_agg_daily_value CHECK (value >= 0)
) PARTITION BY RANGE (bucket);
"""

_INITIAL_PARTITIONS = (
    """SELECT app.create_month_partitions(
    'app', 'agg_hourly', 'timestamptz',
    date_trunc('month', now())::date,
    (date_trunc('month', now()) + interval '2 months')::date
)""",
    """SELECT app.create_month_partitions(
    'app', 'agg_daily', 'date',
    date_trunc('month', now())::date,
    (date_trunc('month', now()) + interval '2 months')::date
)""",
)

_INDEXES = (
    "CREATE INDEX IF NOT EXISTS ix_agg_hourly_kpi_bucket ON app.agg_hourly (kpi_id, bucket)",
    "CREATE INDEX IF NOT EXISTS ix_agg_daily_kpi_bucket  ON app.agg_daily  (kpi_id, bucket)",
)

_COMMENTS = (
    "COMMENT ON TABLE app.agg_hourly IS "
    "'Agregado por hora/unidad/turno/KPI (T10, spec §7.9). Retención 60 meses, "
    "particionado mensual.'",
    "COMMENT ON TABLE app.agg_daily IS "
    "'Agregado por día/unidad/turno/KPI (T10, spec §7.9). Alimenta baseline "
    "«vs ayer». Retención 60 meses, particionado mensual.'",
    "COMMENT ON COLUMN app.agg_hourly.bucket IS 'Inicio de la hora del agregado (UTC).'",
    "COMMENT ON COLUMN app.agg_daily.bucket IS 'Día de datos del agregado (data_date).'",
    "COMMENT ON COLUMN app.agg_hourly.kpi_id IS "
    "'Clave canónica del KPI (p. ej. total_consultas_sifcop) o "
    "''intervenciones'' para series regional/turnos.'",
    "COMMENT ON COLUMN app.agg_hourly.unidad_id IS "
    "'Unidad regional (capital/sur/este/oeste/norte) o '''' cuando no aplica.'",
    "COMMENT ON COLUMN app.agg_hourly.turno_id IS "
    "'Turno operativo (MAÑANA/TARDE/NOCHE) o '''' cuando no aplica.'",
    "COMMENT ON COLUMN app.agg_hourly.baseline_value IS "
    "'Acumulado del periodo de referencia (ayer mismo tramo/turno); NULL si no "
    "hay referencia.'",
)


def upgrade() -> None:
    op.execute(_AGG_HOURLY)
    op.execute(_AGG_DAILY)
    for stmt in _INITIAL_PARTITIONS:
        op.execute(stmt)
    for stmt in _INDEXES:
        op.execute(stmt)
    for stmt in _COMMENTS:
        op.execute(stmt)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS app.agg_hourly CASCADE")
    op.execute("DROP TABLE IF EXISTS app.agg_daily CASCADE")
