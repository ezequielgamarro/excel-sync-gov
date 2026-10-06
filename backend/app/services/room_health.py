"""Panel de salud de sala (spec RNF-07.e, T61).

Vista **interna** para ``platform-admin`` (no expone indicadores operativos,
§2.2.3) con:

- **Última actualización** del dato (``snapshot_current.updated_at``) y **edad
  del dato** global.
- **Estado del webhook** de Google Sheets: última recepción, ``key_id`` vigente,
  degradación y reintentos agotados (reutiliza ``source_health``).
- **Réplicas / storage**: identidad de la réplica que responde, conexiones WSS
  de la sala (presencia en Redis), último ``seq`` y disponibilidad de BD/Redis.

El resultado alimenta ``GET /api/v1/admin/room-health`` (capacidad
``platform.manage_webhook``, deny-by-default).
"""

from __future__ import annotations

import os
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import snapshot_current, webhook_registry
from app.services.bus import get_bus
from app.services.source_health import SourceHealth, build_source_health


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class RoomHealth:
    """Estado de salud de una sala (contrato de ``/admin/room-health``)."""

    room_id: str
    last_update_at: datetime | None
    data_date: str | None
    data_age_seconds: int | None
    last_event_id: str | None
    webhook: SourceHealth | None
    wss_connections: int | None
    last_seq: int | None
    database_ok: bool
    redis_ok: bool
    replica: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        """Representación JSON sin indicadores operativos (§2.2.3)."""
        return {
            "room_id": self.room_id,
            "last_update_at": self.last_update_at.isoformat()
            if self.last_update_at is not None
            else None,
            "data_date": self.data_date,
            "data_age_seconds": self.data_age_seconds,
            "last_event_id": self.last_event_id,
            "webhook": self.webhook.as_dict() if self.webhook is not None else None,
            "wss_connections": self.wss_connections,
            "last_seq": self.last_seq,
            "database_ok": self.database_ok,
            "redis_ok": self.redis_ok,
            "replica": self.replica,
        }


async def _database_ok(session: AsyncSession) -> bool:
    try:
        await session.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def _latest_webhook_id(session: AsyncSession) -> str | None:
    row = (
        await session.execute(
            select(webhook_registry.c.webhook_id)
            .where(
                webhook_registry.c.estado == "activo",
                webhook_registry.c.revoked_at.is_(None),
            )
            .order_by(webhook_registry.c.last_seen_at.desc().nulls_last())
            .limit(1)
        )
    ).first()
    return str(row[0]) if row is not None else None


async def build_room_health(
    session: AsyncSession,
    *,
    room_id: str,
    webhook_id: str | None = None,
    now: datetime | None = None,
) -> RoomHealth:
    """Compone el panel de salud de la sala (RNF-07.e)."""
    momento = _as_utc(now) or datetime.now(timezone.utc)

    snapshot = (
        await session.execute(
            select(
                snapshot_current.c.event_id,
                snapshot_current.c.updated_at,
                snapshot_current.c.data_date,
                snapshot_current.c.seq,
            )
            .order_by(snapshot_current.c.updated_at.desc())
            .limit(1)
        )
    ).first()

    last_update = _as_utc(snapshot.updated_at) if snapshot is not None else None
    data_age = (
        max(0, int((momento - last_update).total_seconds())) if last_update is not None else None
    )

    wid = webhook_id or await _latest_webhook_id(session)
    source = await build_source_health(session, webhook_id=wid, now=momento) if wid else None

    bus = get_bus()
    wss_connections = await bus.connection_count(room_id)
    last_seq = await bus.get_last_seq(room_id)
    redis_ok = wss_connections is not None or last_seq is not None
    database_ok = await _database_ok(session)

    replica = {
        "pid": os.getpid(),
        "hostname": socket.gethostname(),
        "wss_connections": wss_connections,
        "last_seq": last_seq,
    }

    return RoomHealth(
        room_id=room_id,
        last_update_at=last_update,
        data_date=str(snapshot.data_date) if snapshot is not None else None,
        data_age_seconds=data_age,
        last_event_id=str(snapshot.event_id) if snapshot is not None else None,
        webhook=source,
        wss_connections=wss_connections,
        last_seq=last_seq,
        database_ok=database_ok,
        redis_ok=redis_ok,
        replica=replica,
    )
