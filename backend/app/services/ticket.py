"""Ticket WSS de un solo uso (spec §10.3, RNF-03.d, T29).

El ticket encarna ``sub`` + roles + capacidades + ``room_id``, con **TTL 60 s** y
**un solo uso**. Se almacena en Redis y se redime atómicamente con ``GETDEL``
(Redis ≥ 6.2): el primer ``GET`` devuelve el payload y lo elimina, de modo que un
ticket no puede abrir más de una conexión ni reutilizarse. Si Redis no está
disponible, degrada a un almacén en memoria **por proceso** (no distribuido),
con la misma limitación documentada en ``rate_limit``/``replay``.

No se viaja el token de sesión en la URL del WSS (P7, §10.3): solo el ticket
opaco ``tkt_…``.
"""

from __future__ import annotations

import json
import secrets
import time as _time
from typing import Any

import redis.asyncio as aioredis

from app.config import Settings, get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)

_TICKET_PREFIX = "tkt_"


class WsTicketStore:
    """Emisión y redención de tickets de un solo uso (Redis + fallback memoria)."""

    def __init__(self, settings: Settings) -> None:
        self._redis: aioredis.Redis | None = None
        self._memory: dict[str, str] = {}
        self._redis_healthy = bool(settings.redis_url)
        self._ttl = settings.ws_ticket_ttl_seconds

    async def _client(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(get_settings().redis_url, decode_responses=True)
        return self._redis

    async def issue(
        self,
        *,
        sub: str,
        roles: frozenset[str],
        capabilities: frozenset[str],
        room_id: str,
    ) -> str:
        """Emite un ticket opaco de un solo uso (TTL 60 s)."""
        ticket = _TICKET_PREFIX + secrets.token_urlsafe(32)
        payload = json.dumps(
            {
                "sub": sub,
                "roles": sorted(roles),
                "capabilities": sorted(capabilities),
                "room_id": room_id,
                "issued_at": int(_time.time()),
            },
            separators=(",", ":"),
        )
        key = f"ws-ticket:{ticket}"
        if self._redis_healthy:
            try:
                client = await self._client()
                await client.set(key, payload, ex=self._ttl)
                return ticket
            except Exception:
                logger.warning(
                    "ticket_redis_fallback",
                    extra={"event": "ticket", "result": "redis_unavailable"},
                )
                self._redis_healthy = False
        self._memory[ticket] = payload
        if len(self._memory) > 10_000:
            self._memory.clear()
        return ticket

    async def redeem(self, ticket: str) -> dict[str, Any] | None:
        """Redime un ticket (un solo uso). Devuelve ``None`` si es inválido/usado.

        El ``GETDEL`` es atómico: el primer lector consume el ticket; el segundo
        obtiene ``None`` (reutilización → cierre ``4401``, RNF-03.d).
        """
        if not ticket or not ticket.startswith(_TICKET_PREFIX):
            return None
        key = f"ws-ticket:{ticket}"
        raw: bytes | str | None = None
        if self._redis_healthy:
            try:
                client = await self._client()
                raw = await client.getdel(key)
            except Exception:
                logger.warning(
                    "ticket_redis_fallback",
                    extra={"event": "ticket", "result": "redis_unavailable"},
                )
                self._redis_healthy = False
                raw = self._memory.pop(ticket, None)
        else:
            raw = self._memory.pop(ticket, None)
        if raw is None:
            return None
        try:
            parsed = json.loads(raw)
        except ValueError:
            return None
        return parsed if isinstance(parsed, dict) else None

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None


_store: WsTicketStore | None = None


def get_ticket_store() -> WsTicketStore:
    global _store
    if _store is None:
        _store = WsTicketStore(get_settings())
    return _store


async def close_ticket_store() -> None:
    global _store
    if _store is not None:
        await _store.close()
        _store = None
