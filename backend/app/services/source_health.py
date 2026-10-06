"""Salud del origen Google Sheets y modo degradado (spec RF-01.j, T46).

El backend mantiene el estado de salud de cada webhook de Google Sheets:

- **Última recepción** aceptada (``webhook_registry.last_seen_at`` + registro en
  memoria) y **reintentos agotados** reportados por el origen (cabecera
  ``X-Webhook-Retries-Exhausted`` en el siguiente envío exitoso).
- **Modo degradado** (RF-01.j): si transcurren **> 15 min** sin contacto del
  webhook, el origen se marca degradado, se **registra el evento** (auditoría
  ``source.degraded``) y se activa la reconciliación por polling (T45) **sin
  descartar datos** (el envío pendiente del origen se reintenta y la
  reconciliación del backend recupera los cambios).

Reporte de salud: :func:`build_source_health` produce el estado que consume
``GET /api/v1/admin/webhook`` (contrato ``WebhookStatusResponse``), apto para el
``platform-admin`` (no expone indicadores operativos, §2.2.3).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.logging import get_logger
from app.models.tables import webhook_registry, webhook_secret
from app.services.audit import record_audit

logger = get_logger(__name__)

#: Umbral de degradación por defecto (15 min, RF-01.j).
DEFAULT_DEGRADED_THRESHOLD_SECONDS: int = 900

LAST_RESULT_ACCEPTED = "accepted"
LAST_RESULT_REJECTED = "rejected"
LAST_RESULT_NONE = "none"

ACTION_DEGRADED = "source.degraded"
ACTION_RECOVERED = "source.recovered"


def _as_utc(value: datetime | None) -> datetime | None:
    """Normaliza a UTC (asume UTC si viene sin zona)."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class SourceHealth:
    """Estado de salud de un origen (contrato ``WebhookStatusResponse``)."""

    webhook_id: str
    doc_id: str
    active: bool
    current_key_id: str
    last_received_at: datetime | None
    last_result: str
    retries_exhausted: int
    degraded: bool
    age_seconds: int | None

    def as_dict(self) -> dict[str, Any]:
        """Representación JSON (sin indicadores operativos, §2.2.3)."""
        return {
            "webhook_id": self.webhook_id,
            "doc_id": self.doc_id,
            "active": self.active,
            "current_key_id": self.current_key_id,
            "last_received_at": (
                self.last_received_at.isoformat() if self.last_received_at is not None else None
            ),
            "last_result": self.last_result,
            "retries_exhausted": self.retries_exhausted,
            "degraded": self.degraded,
        }


class SourceHealthRegistry:
    """Registro en memoria del estado de salud por ``webhook_id``.

    Es un **acelerador** del estado autoritativo (que persiste en
    ``webhook_registry.last_seen_at``): con N réplicas sin estado, cada réplica
    conoce las recepciones que atendió; el cold start de un monitor reconstruye
    la antigüedad desde la BD.
    """

    def __init__(self, threshold_seconds: int = DEFAULT_DEGRADED_THRESHOLD_SECONDS) -> None:
        self._threshold = threshold_seconds
        self._last_received: dict[str, datetime] = {}
        self._last_result: dict[str, str] = {}
        self._retries: dict[str, int] = {}
        self._degraded: dict[str, bool] = {}

    @property
    def threshold_seconds(self) -> int:
        return self._threshold

    def record_received(
        self,
        webhook_id: str,
        *,
        result: str,
        now: datetime | None = None,
        retries_exhausted: int | None = None,
    ) -> None:
        """Registra una recepción/rechazo y, si aplica, los reintentos agotados."""
        momento = _as_utc(now) or datetime.now(timezone.utc)
        self._last_result[webhook_id] = result
        if result == LAST_RESULT_ACCEPTED:
            self._last_received[webhook_id] = momento
            self._retries[webhook_id] = 0
            self._degraded[webhook_id] = False
        if retries_exhausted is not None and retries_exhausted >= 0:
            self._retries[webhook_id] = retries_exhausted

    def record_retries_exhausted(self, webhook_id: str, count: int) -> None:
        """Fija el contador de reintentos agotados reportado por el origen."""
        self._retries[webhook_id] = max(0, count)

    def last_received_at(self, webhook_id: str) -> datetime | None:
        return self._last_received.get(webhook_id)

    def last_result(self, webhook_id: str) -> str:
        return self._last_result.get(webhook_id, LAST_RESULT_NONE)

    def retries_exhausted(self, webhook_id: str) -> int:
        return self._retries.get(webhook_id, 0)

    def mark_degraded(self, webhook_id: str) -> bool:
        """Marca degradado; devuelve ``True`` solo en la transición (para auditar)."""
        if self._degraded.get(webhook_id, False):
            return False
        self._degraded[webhook_id] = True
        return True

    def mark_recovered(self, webhook_id: str) -> bool:
        """Marca recuperado; devuelve ``True`` solo en la transición (para auditar)."""
        if not self._degraded.get(webhook_id, False):
            return False
        self._degraded[webhook_id] = False
        return True

    def is_flagged_degraded(self, webhook_id: str) -> bool:
        return self._degraded.get(webhook_id, False)


_registry: SourceHealthRegistry | None = None


def get_source_health_registry() -> SourceHealthRegistry:
    """Registro compartido de salud del origen (singleton por proceso)."""
    global _registry
    if _registry is None:
        _registry = SourceHealthRegistry(get_settings().source_degraded_threshold_seconds)
    return _registry


def reset_source_health_registry() -> None:
    """Reinicia el registro (pruebas/arranque)."""
    global _registry
    _registry = None


# =============================================================================
# Persistencia / consulta (BD + registro en memoria)
# =============================================================================
async def _registry_row(
    session: AsyncSession,
    *,
    webhook_id: str | None,
    doc_id: str | None,
) -> Any | None:
    stmt = select(
        webhook_registry.c.webhook_id,
        webhook_registry.c.doc_id,
        webhook_registry.c.estado,
        webhook_registry.c.revoked_at,
        webhook_registry.c.last_seen_at,
        webhook_registry.c.created_at,
    )
    if webhook_id is not None:
        try:
            webhook_uuid = uuid.UUID(webhook_id)
        except (ValueError, AttributeError, TypeError):
            return None
        stmt = stmt.where(webhook_registry.c.webhook_id == webhook_uuid)
    elif doc_id is not None:
        stmt = stmt.where(webhook_registry.c.doc_id == doc_id).order_by(
            webhook_registry.c.created_at.desc()
        )
    else:
        return None
    return (await session.execute(stmt.limit(1))).first()


async def _active_registry_rows(session: AsyncSession) -> list[Any]:
    result = await session.execute(
        select(
            webhook_registry.c.webhook_id,
            webhook_registry.c.doc_id,
            webhook_registry.c.estado,
            webhook_registry.c.revoked_at,
            webhook_registry.c.last_seen_at,
            webhook_registry.c.created_at,
        ).where(
            webhook_registry.c.estado == "activo",
            webhook_registry.c.revoked_at.is_(None),
        )
    )
    return list(result.all())


async def _current_key_id(
    session: AsyncSession, webhook_uuid: uuid.UUID, *, now: datetime
) -> str:
    """``key_id`` vigente del origen (solape de rotación de 24 h, §9.3)."""
    rows = (
        await session.execute(
            select(
                webhook_secret.c.key_id,
                webhook_secret.c.estado,
                webhook_secret.c.not_before,
                webhook_secret.c.not_after,
            ).where(webhook_secret.c.webhook_id == webhook_uuid)
        )
    ).all()
    best = ""
    best_not_before: datetime | None = None
    for key_id, estado, not_before, not_after in rows:
        if str(estado) != "vigente":
            continue
        nb = _as_utc(not_before)
        na = _as_utc(not_after)
        if nb is not None and now < nb:
            continue
        if na is not None and now >= na:
            continue
        if best == "" or (nb is not None and (best_not_before is None or nb > best_not_before)):
            best = str(key_id)
            best_not_before = nb
    return best


async def _touch_registry(
    session: AsyncSession, webhook_uuid: uuid.UUID, *, when: datetime
) -> None:
    await session.execute(
        update(webhook_registry)
        .where(webhook_registry.c.webhook_id == webhook_uuid)
        .values(last_seen_at=when)
    )


async def record_webhook_received(
    session: AsyncSession,
    *,
    webhook_id: str,
    result: str = LAST_RESULT_ACCEPTED,
    now: datetime | None = None,
    retries_exhausted: int | None = None,
    touch_db: bool = True,
) -> None:
    """Registra la recepción (aceptada/rechazada) y persiste el ``last_seen_at``.

    Solo las recepciones **aceptadas** actualizan ``last_seen_at`` (el contrato
    describe la última recepción aceptada).
    """
    momento = _as_utc(now) or datetime.now(timezone.utc)
    registry = get_source_health_registry()
    registry.record_received(
        webhook_id, result=result, now=momento, retries_exhausted=retries_exhausted
    )
    if result == LAST_RESULT_ACCEPTED and touch_db:
        try:
            webhook_uuid = uuid.UUID(webhook_id)
        except (ValueError, AttributeError, TypeError):
            return
        await _touch_registry(session, webhook_uuid, when=momento)


async def build_source_health(
    session: AsyncSession,
    *,
    webhook_id: str | None = None,
    doc_id: str | None = None,
    now: datetime | None = None,
) -> SourceHealth | None:
    """Construye el estado de salud de un origen (o ``None`` si no existe)."""
    row = await _registry_row(session, webhook_id=webhook_id, doc_id=doc_id)
    if row is None:
        return None
    momento = _as_utc(now) or datetime.now(timezone.utc)
    registry = get_source_health_registry()
    wid = str(row.webhook_id)
    active = str(row.estado) == "activo" and row.revoked_at is None

    memory_last = registry.last_received_at(wid)
    db_last = _as_utc(row.last_seen_at)
    last_received = memory_last or db_last

    last_result = registry.last_result(wid)
    if last_result == LAST_RESULT_NONE and last_received is not None:
        last_result = LAST_RESULT_ACCEPTED

    age_seconds: int | None = None
    baseline = last_received or _as_utc(row.created_at)
    if baseline is not None:
        age_seconds = max(0, int((momento - baseline).total_seconds()))

    degraded = bool(active and age_seconds is not None and age_seconds > registry.threshold_seconds)
    current_key_id = await _current_key_id(session, uuid.UUID(wid), now=momento)

    return SourceHealth(
        webhook_id=wid,
        doc_id=str(row.doc_id),
        active=active,
        current_key_id=current_key_id,
        last_received_at=last_received,
        last_result=last_result,
        retries_exhausted=registry.retries_exhausted(wid),
        degraded=degraded,
        age_seconds=age_seconds,
    )


async def evaluate_source_health(
    session: AsyncSession, *, now: datetime | None = None
) -> list[SourceHealth]:
    """Vigila todos los orígenes activos y audita las transiciones de degradación.

    Se ejecuta periódicamente por el supervisor (T45/T46): al superar el umbral
    sin contacto, registra ``source.degraded``; al recuperarse, ``source.recovered``.
    La reconciliación por polling se activa de forma independiente (T45) para no
    descartar datos.
    """
    momento = _as_utc(now) or datetime.now(timezone.utc)
    registry = get_source_health_registry()
    healths: list[SourceHealth] = []
    for row in await _active_registry_rows(session):
        wid = str(row.webhook_id)
        last_received = registry.last_received_at(wid) or _as_utc(row.last_seen_at)
        baseline = last_received or _as_utc(row.created_at)
        age_seconds = (
            max(0, int((momento - baseline).total_seconds())) if baseline is not None else None
        )
        degraded_now = age_seconds is not None and age_seconds > registry.threshold_seconds
        if degraded_now and registry.mark_degraded(wid):
            await record_audit(
                actor="source-supervisor",
                action=ACTION_DEGRADED,
                resource=wid,
                result="degraded",
                session=session,
            )
            logger.warning(
                "source_degraded",
                extra={
                    "event": "source_health",
                    "result": "degraded",
                    "age_seconds": age_seconds,
                },
            )
        elif not degraded_now and registry.mark_recovered(wid):
            await record_audit(
                actor="source-supervisor",
                action=ACTION_RECOVERED,
                resource=wid,
                result="recovered",
                session=session,
            )
            logger.info(
                "source_recovered",
                extra={"event": "source_health", "result": "recovered"},
            )
        health = await build_source_health(session, webhook_id=wid, now=momento)
        if health is not None:
            healths.append(health)
    return healths


async def alert_signals(
    session: AsyncSession, *, now: datetime | None = None
) -> tuple[float | None, int | None]:
    """Señales para las alertas de webhook (RNF-07.d, T60).

    Devuelve ``(segundos_desde_ultimo_webhook, max_reintentos_agotados)``
    agregando **todos** los orígenes activos: el mayor desfase y el mayor
    contador de reintentos agotados (una regla se dispara si cualquier origen la
    cruza). ``(None, None)`` si no hay orígenes activos.
    """
    momento = _as_utc(now) or datetime.now(timezone.utc)
    registry = get_source_health_registry()
    max_age: float | None = None
    max_retries: int | None = None
    for row in await _active_registry_rows(session):
        wid = str(row.webhook_id)
        last_received = registry.last_received_at(wid) or _as_utc(row.last_seen_at)
        baseline = last_received or _as_utc(row.created_at)
        if baseline is not None:
            age = max(0.0, (momento - baseline).total_seconds())
            max_age = age if max_age is None else max(max_age, age)
        retries = registry.retries_exhausted(wid)
        max_retries = retries if max_retries is None else max(max_retries, retries)
    return max_age, max_retries
