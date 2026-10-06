"""base: extensiones y esquemas base

Revision ID: 0001_base
Revises:
Create Date: 2026-10-03

T7 (Fase F1) — marco base de migraciones. NO crea tablas (eso es T8–T14); solo:

1. Habilita las extensiones ``pgcrypto`` (cifrado de columna, §2.2.4 / §7.9)
   y ``uuid-ossp`` (utilidades de generación de UUID), ambas con
   ``CREATE EXTENSION IF NOT EXISTS``.
2. Define la estrategia UUIDv7 (PostgreSQL no la genera de forma nativa hasta
   la v18): crea la función auxiliar ``app.uuidv7()`` como fallback y documenta
   que ``event_id`` se genera en la app con ``uuid6``/``uuid7`` (fuente
   autoritativa). La columna es ``UUID`` nativo. ``uuid-ossp`` no implementa
   v7, por lo que la función v7 se define aquí (RFC 9562).
3. Crea los esquemas/namespaces ``app`` (operativo) y ``audit`` (append-only)
   para aislar el mínimo privilegio del rol ``svc_dashboard`` (§2.2.4/§2.2.6).

Idempotente: up usa ``IF NOT EXISTS`` / ``OR REPLACE``; down usa ``IF EXISTS``.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0001_base"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# =============================================================================
# SQL reutilizable
# =============================================================================

# UUIDv7 (RFC 9562): 48 bits de timestamp Unix en milisegundos (big-endian),
# nibble de versión 7 (byte 6) y nibble de variante 10xx (byte 8); el resto es
# aleatorio. `gen_random_bytes` proviene de pgcrypto. La fuente autoritativa de
# `event_id` es la app (uuid6/uuid7 en Python); esta función es el fallback
# para defaults SQL (ver backend/alembic/README.md).
_UUIDV7_FUNCTION = """
CREATE OR REPLACE FUNCTION app.uuidv7()
RETURNS uuid
LANGUAGE plpgsql
VOLATILE
AS $$
DECLARE
    ts_ms    bigint := (extract(epoch FROM clock_timestamp()) * 1000)::bigint;
    rand     text   := encode(gen_random_bytes(10), 'hex');
    uuid_hex text;
BEGIN
    uuid_hex := lpad(to_hex(ts_ms), 12, '0')  -- 48-bit timestamp (big-endian)
             || '7'                           -- versión 7 (nibble alto del byte 6)
             || substr(rand, 2, 3)            -- byte 6 (nibble bajo) + byte 7
             || '8'                           -- variante 10xx (nibble alto del byte 8)
             || substr(rand, 6, 15);          -- byte 8 (nibble bajo) .. byte 15
    RETURN uuid_hex::uuid;
END;
$$;
"""


def upgrade() -> None:
    # 1. Extensiones ----------------------------------------------------------
    # pgcrypto: cifrado de columna (payload_ciphertext AES-256-GCM, §2.2.4) y
    # primitivas gen_random_bytes / gen_random_uuid.
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    # uuid-ossp: utilidades de generación de UUID (uuid_generate_v1/v4/v5).
    # Se habilita por compatibilidad del stack. NO implementa UUIDv7 (RFC
    # 9562): la estrategia v7 la aporta `app.uuidv7()`, definida más abajo,
    # cuyo material aleatorio proviene de `gen_random_bytes` (pgcrypto).
    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"')

    # 2. Esquemas / namespaces -------------------------------------------------
    # `app`: datos operativos del modelo webhook (§7.9): ingest_event,
    #        snapshot_current, agg_hourly, agg_daily, ranking_snapshot,
    #        webhook_registry, webhook_secret, role_capability.
    # `audit`: bitácora append-only (audit_event), aislada para que el rol de
    #        servicio `svc_dashboard` tenga INSERT+SELECT sin UPDATE/DELETE.
    op.execute("CREATE SCHEMA IF NOT EXISTS app")
    op.execute("CREATE SCHEMA IF NOT EXISTS audit")

    # 3. Función auxiliar UUIDv7 (fallback para defaults SQL) ------------------
    op.execute(_UUIDV7_FUNCTION)


def downgrade() -> None:
    # Orden inverso al upgrade. Cada sentencia es idempotente (IF EXISTS).
    op.execute("DROP FUNCTION IF EXISTS app.uuidv7()")

    # Sin CASCADE: falla si el esquema no está vacío (fail-closed). Al ejecutar
    # `alembic downgrade base` las tablas de T8–T14 ya se habrán revertido antes.
    op.execute("DROP SCHEMA IF EXISTS app")
    op.execute("DROP SCHEMA IF EXISTS audit")

    # Revertir las extensiones habilitadas en upgrade (orden inverso, idempotente).
    # En proveedores gestionados puede no estar permitido desinstalarlas; en ese
    # caso, comentar estas líneas.
    op.execute('DROP EXTENSION IF EXISTS "uuid-ossp"')
    op.execute("DROP EXTENSION IF EXISTS pgcrypto")
