"""svc_dashboard: rol de servicio + particionado + cifrado (T15)

Revision ID: 0009_svc_dashboard
Revises: 0008_role_capability
Create Date: 2026-10-03

T15 (Fase F1) — identidad de servicio de **mínimo privilegio** ``svc_dashboard``
(P10, §2.2.4, §2.2.6), mantenimiento del particionado mensual y cifrado de la
columna ``payload_ciphertext`` con ``pgcrypto`` (RNF-02.a, §7.9).

1) Rol ``svc_dashboard`` — permisos exactos (GRANT/REVOKE)
---------------------------------------------------------------------------
Concede **solo lectura** sobre snapshot/agregados/ranking y sobre las columnas
no sensibles de ``webhook_registry`` (panel de salud), y **append-only** sobre
auditoría. Nunca se otorga ``CREATE`` (sin DDL) ni ``UPDATE``/``DELETE``/
``TRUNCATE``; la negación se hace explícita (mínimo privilegio, fail-closed).

    GRANT  USAGE                      ON SCHEMA app, audit;
    GRANT  SELECT                     ON app.snapshot_current;
    GRANT  SELECT                     ON app.agg_hourly / agg_daily / ranking_snapshot
                                      (padre + particiones);
    GRANT  SELECT (columnas no sensibles) ON app.webhook_registry;
    GRANT  SELECT, INSERT             ON audit.audit_event (padre + particiones);
    GRANT  USAGE, SELECT              ON SEQUENCE audit.audit_event_id_seq;
    REVOKE CREATE                      ON SCHEMA app, audit;
    REVOKE UPDATE, DELETE, TRUNCATE    (todas las tablas de app y audit);

    NO tiene: ingest_event (tabla cruda cifrada), webhook_secret (metadata de
    secretos) ni role_capability. La gestión de secretos de webhook la realiza
    una identidad de escritura separada (fuera de alcance de F1/T15).

La contraseña del rol NO se fija aquí: se inyecta desde el secret manager en el
despliegue (``ALTER ROLE svc_dashboard PASSWORD ...``), nunca se versiona
(RNF-13).

2) Particionado mensual (mantenimiento)
---------------------------------------------------------------------------
``app.roll_partitions()`` crea las particiones futuras (mes actual + 2) y
elimina las caducadas según la retención de §7.9 (ingest_event 90 días; el
resto 60 meses). Debe programarse (pg_cron o job del backend) mensualmente;
tras ejecutarla, llamar ``app.refresh_svc_dashboard_grants()`` para extender
los privilegios a las particiones nuevas (los privilegios del padre NO se
heredan a las hijas en PostgreSQL).

3) Cifrado de columna ``payload_ciphertext`` con ``pgcrypto``
---------------------------------------------------------------------------
``payload_ciphertext`` (bytea, en ``ingest_event``) se cifra en reposo
(AES-256 vía OpenPGP simétrico de ``pgcrypto``). Se exponen dos funciones
auxiliares ``app.encrypt_payload(bytea, text)`` / ``app.decrypt_payload(bytea,
text)`` que reciben la **clave en runtime** (bind parameter): la clave se
inyecta desde el secret manager y **nunca** se almacena en la BD ni en el SQL
versionado (RNF-02.a, §9.1–§9.2). El backend también puede cifrar AES-256-GCM
antes del INSERT; en ningún caso la columna recibe texto claro. ``webhook_secret``
guarda únicamente metadata (``key_id``, estado, fechas), jamás material de
clave (§7.9, RNF-02.e).

Idempotente: rol con guarda de existencia; funciones ``OR REPLACE``; REVOKE es
no-op si el privilegio no existe.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0009_svc_dashboard"
down_revision: Union[str, None] = "0008_role_capability"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# =============================================================================
# SQL
# =============================================================================

# Elimina particiones mensuales con mes anterior a ``p_keep_from`` (el mes más
# antiguo que se conserva). Se apoya en la convención de nombre ``<tabla>_YYYY_MM``.
_DROP_OLD_PARTITIONS = """
CREATE OR REPLACE FUNCTION app.drop_old_partitions(
    p_schema    text,
    p_table     text,
    p_keep_from date
) RETURNS void
LANGUAGE plpgsql
VOLATILE
AS $$
DECLARE
    part record;
BEGIN
    FOR part IN
        SELECT n.nspname AS ns, c.relname AS name
        FROM pg_class p
        JOIN pg_namespace pn ON pn.oid = p.relnamespace
        JOIN pg_inherits i   ON i.inhparent = p.oid
        JOIN pg_class c      ON c.oid = i.inhrelid
        JOIN pg_namespace n  ON n.oid = c.relnamespace
        WHERE pn.nspname = p_schema AND p.relname = p_table
    LOOP
        -- nombre <p_table>_YYYY_MM -> primer día del mes, comparado con el corte
        IF to_date(replace(substr(part.name, length(p_table) + 2), '_', '-'),
                   'YYYY-MM') < date_trunc('month', p_keep_from)::date THEN
            EXECUTE format('DROP TABLE %I.%I', part.ns, part.name);
        END IF;
    END LOOP;
END;
$$;
"""

# Garantiza particiones futuras y aplica retención de §7.9 (programar mensual).
_ROLL_PARTITIONS = """
CREATE OR REPLACE FUNCTION app.roll_partitions() RETURNS void
LANGUAGE plpgsql
VOLATILE
AS $$
DECLARE
    this_month date := date_trunc('month', now())::date;
BEGIN
    -- 1) Particiones futuras (mes actual + 2) => siempre hay destino de escritura.
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

    -- 2) Retención (spec §7.9): elimina particiones más antiguas que el umbral.
    PERFORM app.drop_old_partitions('app',   'ingest_event',
                                    (this_month - interval '2 months')::date);   -- 90 días
    PERFORM app.drop_old_partitions('app',   'agg_hourly',
                                    (this_month - interval '59 months')::date);  -- 60 meses
    PERFORM app.drop_old_partitions('app',   'agg_daily',
                                    (this_month - interval '59 months')::date);  -- 60 meses
    PERFORM app.drop_old_partitions('app',   'ranking_snapshot',
                                    (this_month - interval '59 months')::date);  -- 60 meses
    PERFORM app.drop_old_partitions('audit', 'audit_event',
                                    (this_month - interval '59 months')::date);  -- 60 meses
END;
$$;
"""

# Aplica/reaplica los privilegios de svc_dashboard (padre + particiones).
_REFRESH_GRANTS = """
CREATE OR REPLACE FUNCTION app.refresh_svc_dashboard_grants() RETURNS void
LANGUAGE plpgsql
VOLATILE
AS $$
DECLARE
    r record;
BEGIN
    -- Esquemas (USAGE); sin CREATE => sin DDL.
    GRANT USAGE ON SCHEMA app   TO svc_dashboard;
    GRANT USAGE ON SCHEMA audit TO svc_dashboard;

    -- Operativo: solo lectura sobre snapshot y agregados (padre).
    GRANT SELECT ON app.snapshot_current TO svc_dashboard;
    GRANT SELECT ON app.agg_hourly       TO svc_dashboard;
    GRANT SELECT ON app.agg_daily        TO svc_dashboard;
    GRANT SELECT ON app.ranking_snapshot TO svc_dashboard;

    -- Particiones de los agregados (los privilegios NO se heredan del padre).
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

    -- webhook_registry: SELECT limitado a columnas no sensibles (panel de salud).
    GRANT SELECT (webhook_id, estado, created_at, last_seen_at, revoked_at)
        ON app.webhook_registry TO svc_dashboard;

    -- Auditoría: append-only (INSERT + SELECT), padre y particiones.
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

# Cifrado de columna con pgcrypto: la clave llega en runtime (bind parameter),
# jamás se incrusta en la BD ni en este SQL (RNF-02.a). OpenPGP simétrico AES-256.
_PAYLOAD_CRYPTO = (
    """CREATE OR REPLACE FUNCTION app.encrypt_payload(
    p_plaintext bytea,
    p_key       text
) RETURNS bytea
LANGUAGE sql
STRICT
AS $$
    SELECT pgp_sym_encrypt_bytea(
        p_plaintext,
        p_key,
        'cipher-algo=aes256, compress-algo=0'
    );
$$""",
    """CREATE OR REPLACE FUNCTION app.decrypt_payload(
    p_ciphertext bytea,
    p_key        text
) RETURNS bytea
LANGUAGE sql
STRICT
AS $$
    SELECT pgp_sym_decrypt_bytea(p_ciphertext, p_key);
$$""",
    "COMMENT ON FUNCTION app.encrypt_payload(bytea, text) IS "
    "'Cifra payload_ciphertext (AES-256/OpenPGP pgcrypto). La clave se inyecta "
    "en runtime desde el secret manager y NUNCA se almacena (RNF-02.a).'",
    "COMMENT ON FUNCTION app.decrypt_payload(bytea, text) IS "
    "'Descifra payload_ciphertext con la clave inyectada en runtime; no accesible "
    "para svc_dashboard (tabla cruda fuera de su alcance).'",
)

_CREATE_ROLE = """
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'svc_dashboard') THEN
        CREATE ROLE svc_dashboard LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
    END IF;
END
$$;
"""

# Negación explícita (idempotente: REVOKE es no-op si no existe el privilegio).
_DENY = (
    "REVOKE ALL ON SCHEMA app FROM PUBLIC",
    "REVOKE ALL ON SCHEMA audit FROM PUBLIC",
    "REVOKE CREATE ON SCHEMA app   FROM svc_dashboard",
    "REVOKE CREATE ON SCHEMA audit FROM svc_dashboard",
    "REVOKE UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA app   FROM svc_dashboard",
    "REVOKE UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA audit FROM svc_dashboard",
    "REVOKE ALL ON app.ingest_event    FROM svc_dashboard",
    "REVOKE ALL ON app.webhook_secret  FROM svc_dashboard",
    "REVOKE ALL ON app.role_capability FROM svc_dashboard",
)

_ROLE_COMMENT = """
COMMENT ON ROLE svc_dashboard IS
    'Identidad de servicio de mínimo privilegio (§2.2.4): SELECT sobre '
    'snapshot/agregados/ranking y columnas no sensibles de webhook_registry + '
    'INSERT/SELECT sobre audit_event; sin DDL ni UPDATE/DELETE. Contraseña '
    'inyectada desde el secret manager.';
"""


def upgrade() -> None:
    # 1. Utilidades de particionado (retención + rollover).
    op.execute(_DROP_OLD_PARTITIONS)
    op.execute(_ROLL_PARTITIONS)

    # 2. Rol de servicio (idempotente) y negación explícita.
    op.execute(_CREATE_ROLE)
    for stmt in _DENY:
        op.execute(stmt)

    # 3. Privilegios exactos (función re-ejecutable para particiones nuevas).
    op.execute(_REFRESH_GRANTS)
    op.execute("SELECT app.refresh_svc_dashboard_grants()")

    # 4. Cifrado de columna (pgcrypto, clave en runtime).
    for stmt in _PAYLOAD_CRYPTO:
        op.execute(stmt)

    # 5. Documentación del rol.
    op.execute(_ROLE_COMMENT)


def downgrade() -> None:
    # Cifrado de columna.
    op.execute("DROP FUNCTION IF EXISTS app.decrypt_payload(bytea, text)")
    op.execute("DROP FUNCTION IF EXISTS app.encrypt_payload(bytea, text)")

    # Funciones de mantenimiento (primero las que dependen de otras).
    op.execute("DROP FUNCTION IF EXISTS app.refresh_svc_dashboard_grants()")
    op.execute("DROP FUNCTION IF EXISTS app.roll_partitions()")
    op.execute("DROP FUNCTION IF EXISTS app.drop_old_partitions(text, text, date)")

    # Rol: revoca privilegios (DROP OWNED) y lo elimina.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'svc_dashboard') THEN
                DROP OWNED BY svc_dashboard;
                DROP ROLE svc_dashboard;
            END IF;
        END
        $$;
        """
    )
