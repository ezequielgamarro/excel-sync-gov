"""Auditoría de lecturas del dashboard, muestreada a bajo volumen (RNF-08.e, T62).

Registra la **primera visualización** de cada operador por **día de datos** y por
sala, asociando ``sub``, ``room_id``, ``data_date`` y ``event_id`` (RF-02.j,
AM-13). No se audita por frame: una vez vista la combinación
``(sub, room_id, data_date)`` no se vuelve a registrar, y cada **exportación**
se audita por separado (en ``app/api/dashboard.py``).

El registro es *fail-open* para la lectura (nunca impide ver el dato) pero
*fail-closed* para la trazabilidad: si el marcador no se puede fijar se asume
primera vista y se audita igualmente (es preferible duplicar que perder rastro).
Usa Redis (``SET NX`` con TTL) cuando está configurado —de modo que N réplicas
comparten la deduplicación— y degrada a memoria por proceso.
"""

from __future__ import annotations

from typing import Any

from app.config import get_settings
from app.core.logging import get_logger
from app.services.audit import record_audit

logger = get_logger(__name__)

ACTION_FIRST_VIEW = "dashboard.view.first"
#: TTL del marcador de primera vista (cubre con holgura el día de datos).
FIRST_VIEW_TTL_SECONDS = 172800

_seen: set[tuple[str, str, str]] = set()
_redis: Any = None
_redis_checked = False


def _key(sub: str, room_id: str, data_date: str) -> str:
    return f"read:first:{sub}:{room_id}:{data_date}"


async def _redis_client() -> Any:
    """Cliente Redis perezoso (o ``None`` si no hay URL configurada)."""
    global _redis, _redis_checked
    settings = get_settings()
    redis_url = getattr(settings, "redis_url", "")
    if not redis_url:
        return None
    if not _redis_checked:
        _redis_checked = True
        try:
            import redis.asyncio as aioredis

            _redis = aioredis.from_url(redis_url, decode_responses=True)
        except Exception:
            _redis = None
    return _redis


async def _mark_first(sub: str, room_id: str, data_date: str) -> bool:
    """Marca la combinación y devuelve ``True`` si es la primera vez."""
    client = await _redis_client()
    if client is not None:
        try:
            created = await client.set(
                _key(sub, room_id, data_date), "1", nx=True, ex=FIRST_VIEW_TTL_SECONDS
            )
            return bool(created)
        except Exception:  # pragma: no cover - degradación a memoria
            pass
    marker = (sub, room_id, data_date)
    if marker in _seen:
        return False
    _seen.add(marker)
    return True


async def record_first_view(
    *,
    sub: str,
    room_id: str,
    data_date: str,
    event_id: str,
    ip: str = "",
    user_agent: str = "",
) -> bool:
    """Audita la primera visualización por operador/día de datos (RNF-08.e).

    Devuelve ``True`` si se generó un evento de auditoría (primera vista) y
    ``False`` si ya se había registrado (deduplicado, sin ruido por frame). La
    escritura usa una sesión propia (commit inmediato, RNF-08.a), igual que el
    resto de la auditoría.
    """
    if not await _mark_first(sub, room_id, data_date):
        return False
    resource = f"room={room_id};data_date={data_date};event_id={event_id}"
    await record_audit(
        actor=sub,
        action=ACTION_FIRST_VIEW,
        resource=resource,
        result="success",
        ip=ip,
        user_agent=user_agent,
    )
    return True


def reset_first_view_registry() -> None:
    """Limpia el registro de primeras vistas (pruebas/arranque)."""
    _seen.clear()
