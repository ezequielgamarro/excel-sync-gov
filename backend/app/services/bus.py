"""Distribución en tiempo real: Redis pub/sub + ``seq`` por sala (spec §3.3, T28).

Fan-out por ``room_id`` (una instancia = una sala; OD-06/OOS-11) sobre un canal
Redis ``room:{room_id}``. El backend corre con **N réplicas sin estado**
(RNF-06.c): cada réplica se suscribe a los canales de las salas que sirve y la
publicación es independiente de la réplica, de modo que cualquier instancia que
reciba el evento lo reemite/consume sin duplicar.

El ``seq`` es **monótono por sala** (RNF-11.b): se asigna de forma **atómica**
con ``INCR`` sobre una clave por ``room_id`` (``seq:{room_id}``). El ``seq``
persistido por la ingesta (secuencia de BD, F3/T26) actúa de **suelo**: la clave
Redis nunca queda por debajo de él, de forma que ``hello.last_seq`` y la
detección del ``409`` de cold start (§10.4) son consistentes con lo persistido,
pero el contador de sala siempre avanza de a uno y sin repetir aunque la
publicación provenga de réplicas distintas. Redis se usa también para la
**presencia/conteo de conexiones** por sala (§3.3).

Degradación controlada (RNF-06.e): si Redis no está disponible, la publicación
se omite (no falla la ingesta), el ``seq`` cae de vuelta al asignado por la BD y
el dashboard degrada a polling; el cold start sigue leyendo PostgreSQL.
"""

from __future__ import annotations

import asyncio
import json
import time as _time
from datetime import date, datetime, timezone
from typing import Any, AsyncIterator

import redis.asyncio as aioredis
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.logging import get_logger
from app.services.aggregate import enrich_payload

logger = get_logger(__name__)

SCHEMA_VERSION = "1.0.0"
MESSAGE_TYPE_SNAPSHOT = "indicators.snapshot"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(ts: datetime) -> str:
    return ts.astimezone(timezone.utc).isoformat()


def tz_offset_minutes(tz: str, at: datetime) -> int:
    """Offset en minutos de ``tz`` respecto a UTC para el instante ``at``."""
    try:
        from zoneinfo import ZoneInfo

        offset = at.astimezone(ZoneInfo(tz)).utcoffset()
        return int(offset.total_seconds() // 60) if offset is not None else 0
    except Exception:
        return 0


def attach_freshness_quality(
    payload: dict[str, Any],
    *,
    sheet_modified_at: str,
    accepted_at: datetime,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Añade ``freshness`` y ``quality`` (§7.7) al payload del sobre.

    ``stale`` es un *hint* (la decisión final la toma el cliente con su reloj);
    aquí se computa contra el umbral de 120 s (§13, RF-05.h).
    """
    now = now or _now_utc()
    age = max(0, int((now - accepted_at).total_seconds()))
    enriched = dict(payload)
    enriched["freshness"] = {
        "last_event_ts": _iso(accepted_at),
        "sheet_modified_at": sheet_modified_at,
        "stale": age > 120,
        "age_seconds": age,
    }
    enriched["quality"] = {
        "partial": False,
        "source_rows": 5,
        "warnings": [],
    }
    return enriched


def build_snapshot_message(
    *,
    document: dict[str, Any],
    seq: int,
    room_id: str,
    webhook_id: str,
    correlation_id: str,
    payload: dict[str, Any],
    accepted_at: datetime,
    tz: str,
) -> dict[str, Any]:
    """Construye el sobre ``indicators.snapshot`` completo (§7.2, contract 1.0.0).

    ``source`` identifica al **origen** (webhook de Google Sheets / Apps Script):
    ``webhook_id`` + ``doc_id`` + ``content_sha256`` + ``sheet_modified_at``. No
    existe la noción de "agente": la identidad del emisor es el ``webhook_id``.
    """
    return {
        "schema_version": str(document.get("schema_version") or SCHEMA_VERSION),
        "type": MESSAGE_TYPE_SNAPSHOT,
        "event_id": str(document.get("event_id") or ""),
        "seq": seq,
        "room_id": room_id,
        "ts": _iso(accepted_at),
        "tz": tz,
        "tz_offset_minutes": tz_offset_minutes(tz, accepted_at),
        "data_date": str(document.get("data_date") or ""),
        "source": {
            "webhook_id": webhook_id,
            "doc_id": str(document.get("doc_id") or ""),
            "content_sha256": str(document.get("content_sha256") or ""),
            "sheet_modified_at": str(document.get("sheet_modified_at") or ""),
        },
        "payload": payload,
        "correlation_id": correlation_id,
    }


class RoomBus:
    """Pub/sub por sala sobre Redis (``redis.asyncio``), con fallback a no-op.

    Igual que ``replay``/``rate_limit``/``activation``, Redis es la base
    autoritativa de la distribución en vivo; si cae, el fan-out se degrada (el
    dashboard hace polling, RNF-06.e) sin romper la ingesta. El ``seq`` de sala y
    la presencia también viven en Redis, por lo que las N réplicas comparten
    estado (RNF-06.c).
    """

    def __init__(self, settings: Settings, *, client: aioredis.Redis | None = None) -> None:
        self._settings = settings
        self._redis: aioredis.Redis | None = client
        self._owns_client = client is None
        # Sin URL configurada el bus queda deshabilitado (degradación a polling);
        # un cliente inyectado (tests) se considera siempre disponible.
        self._redis_configured = client is not None or bool(settings.redis_url)
        self._redis_healthy = self._redis_configured
        self._retry_redis_at = 0.0

    def channel(self, room_id: str) -> str:
        """Canal pub/sub de la sala (fan-out a todas las réplicas)."""
        return f"room:{room_id}"

    def seq_key(self, room_id: str) -> str:
        """Clave del ``seq`` monótono por sala (``INCR`` atómico)."""
        return f"seq:{room_id}"

    def presence_key(self, room_id: str) -> str:
        """Conjunto de conexiones WSS de la sala (§3.3, presencia/conteo)."""
        return f"presence:{room_id}"

    async def _client(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(
                self._settings.redis_url, decode_responses=True
            )
        return self._redis

    def _mark_unhealthy(self) -> None:
        self._redis_healthy = False
        self._retry_redis_at = _time.monotonic() + 30.0

    def _maybe_retry(self) -> None:
        if (
            not self._redis_healthy
            and self._redis_configured
            and _time.monotonic() >= self._retry_redis_at
        ):
            self._redis_healthy = True

    async def next_seq(self, room_id: str, *, floor: int = 0) -> int | None:
        """Asigna el siguiente ``seq`` monótono de la sala de forma atómica.

        Usa ``INCR`` (atómico, seguro con N réplicas: dos publicaciones
        concurrentes nunca obtienen el mismo valor). ``floor`` es el ``seq`` ya
        persistido en BD por la ingesta; si el contador Redis quedara por debajo,
        se eleva a ese suelo para que el orden de aplicación coincida con el cold
        start. Devuelve ``None`` si Redis no está disponible (el llamador cae de
        vuelta al ``seq`` de BD).
        """
        self._maybe_retry()
        if not self._redis_healthy:
            return None
        try:
            client = await self._client()
            value = int(await client.incr(self.seq_key(room_id)))
            if value < floor:
                await client.set(self.seq_key(room_id), str(floor))
                value = floor
            return value
        except Exception:
            logger.warning(
                "bus_redis_fallback", extra={"event": "bus", "result": "redis_unavailable"}
            )
            self._mark_unhealthy()
            return None

    async def get_last_seq(self, room_id: str) -> int | None:
        """Último ``seq`` de la sala (``None`` si Redis no está disponible)."""
        self._maybe_retry()
        if not self._redis_healthy:
            return None
        try:
            client = await self._client()
            value = await client.get(self.seq_key(room_id))
            return int(value) if value else None
        except Exception:
            logger.warning(
                "bus_redis_fallback", extra={"event": "bus", "result": "redis_unavailable"}
            )
            self._mark_unhealthy()
            return None

    async def publish(self, room_id: str, message: dict[str, Any]) -> bool:
        """Publica el sobre en ``room:{room_id}``. Devuelve ``False`` si Redis cayó."""
        self._maybe_retry()
        if not self._redis_healthy:
            return False
        try:
            client = await self._client()
            await client.publish(
                self.channel(room_id), json.dumps(message, separators=(",", ":"))
            )
            return True
        except Exception:
            logger.warning(
                "bus_redis_fallback", extra={"event": "bus", "result": "redis_unavailable"}
            )
            self._mark_unhealthy()
            return False

    async def subscribe(self, *room_ids: str) -> AsyncIterator[dict[str, Any]]:
        """Iterador de mensajes de las salas servidas por esta réplica.

        Cada instancia se suscribe a los canales de las salas que sirve
        (``room:{room_id}``); con varias réplicas, Redis entrega cada mensaje a
        todas las suscritas (fan-out, RNF-04.d/RNF-06.c). Reintenta
        indefinidamente si Redis no está disponible: no produce mensajes y el
        cliente degrada a polling si detecta falta de actividad (RNF-05.d).
        """
        channels = [self.channel(room_id) for room_id in room_ids if room_id]
        if not channels:
            return
        while True:
            self._maybe_retry()
            if not self._redis_healthy:
                await asyncio.sleep(1.0)
                continue
            pubsub_client: aioredis.Redis | None = None
            try:
                pubsub_client = aioredis.from_url(
                    self._settings.redis_url, decode_responses=True
                )
                await pubsub_client.ping()
                pubsub = pubsub_client.pubsub()
                await pubsub.subscribe(*channels)
                async for item in pubsub.listen():
                    if item.get("type") != "message":
                        continue
                    data = item.get("data")
                    if not isinstance(data, str):
                        continue
                    try:
                        yield json.loads(data)
                    except ValueError:
                        continue
            except Exception:
                logger.warning(
                    "bus_redis_fallback", extra={"event": "bus", "result": "redis_unavailable"}
                )
                self._mark_unhealthy()
            finally:
                if pubsub_client is not None:
                    try:
                        await pubsub_client.aclose()
                    except Exception:
                        pass

    # --- Presencia / conteo de conexiones por sala (§3.3, RNF-06.c) ----------
    async def register_connection(self, room_id: str, connection_id: str) -> int | None:
        """Registra una conexión WSS y devuelve el total de la sala (o ``None``)."""
        self._maybe_retry()
        if not self._redis_healthy:
            return None
        try:
            client = await self._client()
            key = self.presence_key(room_id)
            await client.sadd(key, connection_id)
            return int(await client.scard(key))
        except Exception:
            self._mark_unhealthy()
            return None

    async def unregister_connection(self, room_id: str, connection_id: str) -> int | None:
        """Da de baja una conexión WSS y devuelve el total restante (o ``None``)."""
        self._maybe_retry()
        if not self._redis_healthy:
            return None
        try:
            client = await self._client()
            key = self.presence_key(room_id)
            await client.srem(key, connection_id)
            return int(await client.scard(key))
        except Exception:
            self._mark_unhealthy()
            return None

    async def connection_count(self, room_id: str) -> int | None:
        """Número de conexiones WSS activas de la sala (o ``None`` si Redis cayó)."""
        self._maybe_retry()
        if not self._redis_healthy:
            return None
        try:
            client = await self._client()
            return int(await client.scard(self.presence_key(room_id)))
        except Exception:
            self._mark_unhealthy()
            return None

    async def close(self) -> None:
        if self._redis is not None and self._owns_client:
            await self._redis.aclose()
        self._redis = None


_bus: RoomBus | None = None


def get_bus() -> RoomBus:
    """Devuelve el bus de sala compartido (singleton por proceso)."""
    global _bus
    if _bus is None:
        _bus = RoomBus(get_settings())
    return _bus


async def close_bus() -> None:
    global _bus
    if _bus is not None:
        await _bus.close()
        _bus = None


async def publish_snapshot(
    *,
    session: AsyncSession,
    document: dict[str, Any],
    seq: int,
    room_id: str,
    webhook_id: str,
    correlation_id: str,
    accepted_at: datetime,
) -> None:
    """Hook de redistribución de la ingesta (T26/T28): enriquece, construye y publica.

    - Enriquecimiento autoritativo de "vs ayer" (``aggregate.enrich_payload``).
    - Añadido de ``freshness``/``quality``.
    - Asignación del ``seq`` monótono de la sala (Redis ``INCR``; el ``seq`` de BD
      actúa de suelo) y publicación en ``room:{room_id}`` para el fan-out a las
      N réplicas vía Redis.
    """
    settings = get_settings()
    tz = str(document.get("tz") or settings.canonical_timezone)
    data_date_raw = document.get("data_date")
    try:
        data_date = date.fromisoformat(str(data_date_raw))
    except (ValueError, TypeError):
        data_date = accepted_at.date()

    raw_payload = document.get("payload") or {}
    payload = await enrich_payload(
        session,
        raw_payload,
        data_date=data_date,
        as_of=accepted_at,
    )
    payload = attach_freshness_quality(
        payload,
        sheet_modified_at=str(document.get("sheet_modified_at") or ""),
        accepted_at=accepted_at,
    )

    bus = get_bus()
    # ``seq`` autoritativo de la sala: Redis INCR (atómico, seguro entre réplicas)
    # con el ``seq`` persistido como suelo; si Redis cae, se conserva el de BD.
    effective_seq = await bus.next_seq(room_id, floor=seq)
    if effective_seq is None:
        effective_seq = seq

    message = build_snapshot_message(
        document=document,
        seq=effective_seq,
        room_id=room_id,
        webhook_id=webhook_id,
        correlation_id=correlation_id,
        payload=payload,
        accepted_at=accepted_at,
        tz=tz,
    )
    await bus.publish(room_id, message)
