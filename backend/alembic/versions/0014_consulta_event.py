"""consulta_event: detalle de la hoja «CONSULTAS» (20 columnas oficiales)

Revision ID: 0014_consulta_event
Revises: 0013_platform_admin_view_live
Create Date: 2026-10-05

Sincroniza el modelo de datos con la planilla oficial de la Jefatura: crea la
tabla ``app.consulta_event`` con las **20 columnas exactas** de la hoja
«CONSULTAS» más los campos técnicos de trazabilidad del evento de origen
(``event_id``/``doc_id``/``row_index``/``seq``/``received_at``/``correlation_id``).

- Columnas de datos (orden de la hoja):
  ``fecha_consulta``, ``hora_consulta``, ``turno``, ``jerarquia``,
  ``personal_policial``, ``jefatura_regional``, ``dependencias``,
  ``tipo_consulta``, ``identificacion``, ``tipo_arma_vehiculo``, ``resultado``,
  ``causas_penales``, ``registro_legajo``, ``autoridad_judicial``,
  ``sistema_utilizado``, ``tramite_devuelto``, ``hora_resp``,
  ``personal_que_informa``, ``cargo``, ``operativos_preventivos``.
- ``fecha_consulta`` es la clave de partición (``RANGE`` mensual, retención
  60 meses). La PK incluye la clave de partición (``fecha_consulta``), como exige
  PostgreSQL en tablas particionadas.
- El índice único ``(event_id, row_index, fecha_consulta)`` habilita la
  idempotencia del INSERT (``ON CONFLICT DO NOTHING``) ante reintentos.
- Índices de agrupación por ``turno``, ``jefatura_regional``, ``resultado`` y
  ``causas_penales`` (alimentan los gráficos/KPIs del dashboard).

Además re-define, de forma idempotente, ``app.roll_partitions()`` y
``app.refresh_svc_dashboard_grants()`` para incluir la nueva tabla (particiones
futuras + privilegios de lectura ``svc_dashboard``).
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0014_consulta_event"
down_revision: Union[str, None] = "0013_platform_admin_view_live"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CONSULTA_EVENT = """
CREATE TABLE IF NOT EXISTS app.consulta_event (
    event_id              uuid        NOT NULL,
    doc_id                text        NOT NULL,
    row_index             integer     NOT NULL,
    seq                   bigint      NOT NULL,
    received_at           timestamptz NOT NULL DEFAULT now(),
    correlation_id        text,
    fecha_consulta        date        NOT NULL,
    hora_consulta         text,
    turno                 text,
    jerarquia             text,
    personal_policial     text,
    jefatura_regional     text,
    dependencias          text,
    tipo_consulta         text,
    identificacion        text,
    tipo_arma_vehiculo    text,
    resultado             text,
    causas_penales        text,
    registro_legajo       text,
    autoridad_judicial    text,
    sistema_utilizado     text,
    tramite_devuelto      text,
    hora_resp             text,
    personal_que_informa  text,
    cargo                 text,
    operativos_preventivos text,
    CONSTRAINT pk_consulta_event PRIMARY KEY (fecha_consulta, event_id, row_index)
) PARTITION BY RANGE (fecha_consulta);
"""

_INITIAL_PARTITIONS = """
SELECT app.create_month_partitions(
    'app', 'consulta_event', 'date',
    date_trunc('month', now())::date,
    (date_trunc('month', now()) + interval '2 months')::date
);
"""

_INDEXES = (
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_consulta_event_row "
    "ON app.consulta_event (event_id, row_index, fecha_consulta)",
    "CREATE INDEX IF NOT EXISTS ix_consulta_event_fecha_turno "
    "ON app.consulta_event (fecha_consulta, turno)",
    "CREATE INDEX IF NOT EXISTS ix_consulta_event_fecha_jefatura "
    "ON app.consulta_event (fecha_consulta, jefatura_regional)",
    "CREATE INDEX IF NOT EXISTS ix_consulta_event_fecha_resultado "
    "ON app.consulta_event (fecha_consulta, resultado)",
    "CREATE INDEX IF NOT EXISTS ix_consulta_event_causas "
    "ON app.consulta_event (fecha_consulta, causas_penales)",
)

# roll_partitions() con la nueva tabla incluida (idempotente: OR REPLACE).
_ROLL_PARTITIONS = """
CREATE OR REPLACE FUNCTION app.roll_partitions() RETURNS void
LANGUAGE plpgsql
VOLATILE
AS $$
DECLARE
    this_month date := date_trunc('month', now())::date;
BEGIN
    PERFORM app.create_month_partitions('app',   'ingest_event',     'timestamptz',
                                        this_month, (this_month + interval '2 months')::date);
    PERFORM app.create_month_partitions('app',   'agg_hourly',       'timestamptz',
                                        this_month, (this_month + interval '2 months')::date);
    PERFORM app.create_month_partitions('app',   'agg_daily',        'date',
                                        this_month, (this_month + interval '2 months')::date);
    PERFORM app.create_month_partitions('app',   'ranking_snapshot', 'date',
                                        this_month, (this_month + interval '2 months')::date);
    PERFORM app.create_month_partitions('app',   'consulta_event',   'date',
                                        this_month, (this_month + interval '2 months')::date);
    PERFORM app.create_month_partitions('audit', 'audit_event',      'timestamptz',
                                        this_month, (this_month + interval '2 months')::date);

    PERFORM app.drop_old_partitions('app',   'ingest_event',
                                    (this_month - interval '2 months')::date);
    PERFORM app.drop_old_partitions('app',   'agg_hourly',
                                    (this_month - interval '59 months')::date);
    PERFORM app.drop_old_partitions('app',   'agg_daily',
                                    (this_month - interval '59 months')::date);
    PERFORM app.drop_old_partitions('app',   'ranking_snapshot',
                                    (this_month - interval '59 months')::date);
    PERFORM app.drop_old_partitions('app',   'consulta_event',
                                    (this_month - interval '59 months')::date);
    PERFORM app.drop_old_partitions('audit', 'audit_event',
                                    (this_month - interval '59 months')::date);
END;
$$;
"""

# refresh_svc_dashboard_grants() con SELECT sobre consulta_event (padre + hijas).
_REFRESH_GRANTS = """
CREATE OR REPLACE FUNCTION app.refresh_svc_dashboard_grants() RETURNS void
LANGUAGE plpgsql
VOLATILE
AS $$
DECLARE
    r record;
BEGIN
    GRANT USAGE ON SCHEMA app   TO svc_dashboard;
    GRANT USAGE ON SCHEMA audit TO svc_dashboard;

    GRANT SELECT ON app.snapshot_current TO svc_dashboard;
    GRANT SELECT ON app.agg_hourly       TO svc_dashboard;
    GRANT SELECT ON app.agg_daily        TO svc_dashboard;
    GRANT SELECT ON app.ranking_snapshot TO svc_dashboard;
    GRANT SELECT ON app.consulta_event   TO svc_dashboard;

    FOR r IN
        SELECT n.nspname AS ns, c.relname AS rel
        FROM pg_class p
        JOIN pg_namespace pn ON pn.oid = p.relnamespace
        JOIN pg_inherits i   ON i.inhparent = p.oid
        JOIN pg_class c      ON c.oid = i.inhrelid
        JOIN pg_namespace n  ON n.oid = c.relnamespace
        WHERE pn.nspname = 'app'
          AND p.relname IN ('agg_hourly', 'agg_daily', 'ranking_snapshot', 'consulta_event')
    LOOP
        EXECUTE format('GRANT SELECT ON %I.%I TO svc_dashboard', r.ns, r.rel);
    END LOOP;

    GRANT SELECT (webhook_id, estado, created_at, last_seen_at, revoked_at)
        ON app.webhook_registry TO svc_dashboard;

    GRANT SELECT, INSERT ON audit.audit_event TO svc_dashboard;
    FOR r IN
        SELECT n.nspname AS ns, c.relname AS rel
        FROM pg_class p
        JOIN pg_namespace pn ON pn.oid = p.relnamespace
        JOIN pg_inherits i   ON i.inhparent = p.oid
        JOIN pg_class c      ON c.oid = i.inhrelid
        JOIN pg_namespace n  ON n.oid = c.relnamespace
        WHERE pn.nspname = 'audit' AND p.relname = 'audit_event'
    LOOP
        EXECUTE format('GRANT SELECT, INSERT ON %I.%I TO svc_dashboard', r.ns, r.rel);
    END LOOP;
    GRANT USAGE, SELECT ON SEQUENCE audit.audit_event_id_seq TO svc_dashboard;
END;
$$;
"""

# Definiciones previas (0009) para revertir sin dejar funciones rotas.
_ROLL_PARTITIONS_BASE = """
CREATE OR REPLACE FUNCTION app.roll_partitions() RETURNS void
LANGUAGE plpgsql
VOLATILE
AS $$
DECLARE
    this_month date := date_trunc('month', now())::date;
BEGIN
    PERFORM app.create_month_partitions('app',   'ingest_event',     'timestamptz',
                                        this_month, (this_month + interval '2 months')::date);
    PERFORM app.create_month_partitions('app',   'agg_hourly',       'timestamptz',
                                        this_month, (this_month + interval '2 months')::date);
    PERFORM app.create_month_partitions('app',   'agg_daily',        'date',
                                        this_month, (this_month + interval '2 months')::date);
    PERFORM app.create_month_partitions('app',   'ranking_snapshot', 'date',
                                        this_month, (this_month + interval '2 months')::date);
    PERFORM app.create_month_partitions('audit', 'audit_event',      'timestamptz',
                                        this_month, (this_month + interval '2 months')::date);

    PERFORM app.drop_old_partitions('app',   'ingest_event',
                                    (this_month - interval '2 months')::date);
    PERFORM app.drop_old_partitions('app',   'agg_hourly',
                                    (this_month - interval '59 months')::date);
    PERFORM app.drop_old_partitions('app',   'agg_daily',
                                    (this_month - interval '59 months')::date);
    PERFORM app.drop_old_partitions('app',   'ranking_snapshot',
                                    (this_month - interval '59 months')::date);
    PERFORM app.drop_old_partitions('audit', 'audit_event',
                                    (this_month - interval '59 months')::date);
END;
$$;
"""

_REFRESH_GRANTS_BASE = """
CREATE OR REPLACE FUNCTION app.refresh_svc_dashboard_grants() RETURNS void
LANGUAGE plpgsql
VOLATILE
AS $$
DECLARE
    r record;
BEGIN
    GRANT USAGE ON SCHEMA app   TO svc_dashboard;
    GRANT USAGE ON SCHEMA audit TO svc_dashboard;

    GRANT SELECT ON app.snapshot_current TO svc_dashboard;
    GRANT SELECT ON app.agg_hourly       TO svc_dashboard;
    GRANT SELECT ON app.agg_daily        TO svc_dashboard;
    GRANT SELECT ON app.ranking_snapshot TO svc_dashboard;

    FOR r IN
        SELECT n.nspname AS ns, c.relname AS rel
        FROM pg_class p
        JOIN pg_namespace pn ON pn.oid = p.relnamespace
        JOIN pg_inherits i   ON i.inhparent = p.oid
        JOIN pg_class c      ON c.oid = i.inhrelid
        JOIN pg_namespace n  ON n.oid = c.relnamespace
        WHERE pn.nspname = 'app'
          AND p.relname IN ('agg_hourly', 'agg_daily', 'ranking_snapshot')
    LOOP
        EXECUTE format('GRANT SELECT ON %I.%I TO svc_dashboard', r.ns, r.rel);
    END LOOP;

    GRANT SELECT (webhook_id, estado, created_at, last_seen_at, revoked_at)
        ON app.webhook_registry TO svc_dashboard;

    GRANT SELECT, INSERT ON audit.audit_event TO svc_dashboard;
    FOR r IN
        SELECT n.nspname AS ns, c.relname AS rel
        FROM pg_class p
        JOIN pg_namespace pn ON pn.oid = p.relnamespace
        JOIN pg_inherits i   ON i.inhparent = p.oid
        JOIN pg_class c      ON c.oid = i.inhrelid
        JOIN pg_namespace n  ON n.oid = c.relnamespace
        WHERE pn.nspname = 'audit' AND p.relname = 'audit_event'
    LOOP
        EXECUTE format('GRANT SELECT, INSERT ON %I.%I TO svc_dashboard', r.ns, r.rel);
    END LOOP;
    GRANT USAGE, SELECT ON SEQUENCE audit.audit_event_id_seq TO svc_dashboard;
END;
$$;
"""

_COMMENT = (
    "COMMENT ON TABLE app.consulta_event IS "
    "'Detalle de la hoja «CONSULTAS» de la planilla oficial (20 columnas). "
    "Fuente granular para las agrupaciones por resultado, causas_penales, "
    "jefatura_regional y turno. Retención 60 meses, particionado por fecha_consulta.'",
    "COMMENT ON COLUMN app.consulta_event.row_index IS "
    "'Índice de la fila dentro del evento (junto a event_id identifica la fila).'",
    "COMMENT ON COLUMN app.consulta_event.turno IS "
    "'Turno operativo (MAÑANA/TARDE/NOCHE) tal como llega de la planilla.'",
    "COMMENT ON COLUMN app.consulta_event.resultado IS "
    "'Resultado de la consulta (agrupación de KPIs del dashboard).'",
    "COMMENT ON COLUMN app.consulta_event.causas_penales IS "
    "'Causas penales asociadas (agrupación de KPIs del dashboard).'",
    "COMMENT ON COLUMN app.consulta_event.jefatura_regional IS "
    "'Jefatura/unidad regional (agrupación del dashboard).'",
)


def upgrade() -> None:
    op.execute(_CONSULTA_EVENT)
    op.execute(_INITIAL_PARTITIONS)
    for stmt in _INDEXES:
        op.execute(stmt)
    op.execute(_ROLL_PARTITIONS)
    op.execute(_REFRESH_GRANTS)
    op.execute("SELECT app.refresh_svc_dashboard_grants()")
    for stmt in _COMMENT:
        op.execute(stmt)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS app.consulta_event CASCADE")
    op.execute(_ROLL_PARTITIONS_BASE)
    op.execute(_REFRESH_GRANTS_BASE)
    op.execute("SELECT app.refresh_svc_dashboard_grants()")
