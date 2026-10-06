"""Modelos de dominio y ORM (SQLAlchemy Core).

Las migraciones de Alembic (T7–T15) crean el esquema a mano; ``tables`` es la
proyección Core usada por la capa de persistencia (F3). Véase
``backend/docs/schema.md`` para el modelo completo.
"""

from app.models.tables import (
    APP_SCHEMA,
    AUDIT_SCHEMA,
    KPIS,
    REGIONAL_UNITS,
    TURNOS,
    agg_daily,
    agg_hourly,
    audit_event,
    ingest_event,
    keyring,
    ranking_snapshot,
    role_capability,
    snapshot_current,
    webhook_registry,
    webhook_secret,
)

__all__ = [
    "APP_SCHEMA",
    "AUDIT_SCHEMA",
    "KPIS",
    "REGIONAL_UNITS",
    "TURNOS",
    "agg_daily",
    "agg_hourly",
    "audit_event",
    "ingest_event",
    "keyring",
    "ranking_snapshot",
    "role_capability",
    "snapshot_current",
    "webhook_registry",
    "webhook_secret",
]
