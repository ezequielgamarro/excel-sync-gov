"""Re-verificación de rol y lista de revocación (spec RNF-03.c/e/h, T37).

La autorización se evalúa **en la apertura** del WSS y se **re-verifica
periódicamente**: si un operador pierde su rol o se desactiva la cuenta, el
backend cierra la conexión en **≤ 30 s** (RNF-03.e).

Mecanismos:

- ``RevocationStore``: lista de ``sub`` revocados (Redis, con fallback en
  memoria). Los cambios de rol/estado en la gestión de usuarios locales (T36)
  marcan el ``sub``; el
  WSS comprueba la lista en cada latido (≈15 s ≤ 30 s) y cierra ``4003``.
- ``ReauthRegistry``: instantánea de capacidades por sesión WSS. Si el backend
  observa un cambio de capacidades que retira ``dash.view.live``, cierra el
  socket; si cambian los roles pero el acceso sigue autorizado, cierra ``4403``
  para forzar re-autenticación ordenada.

Ambos usan Redis cuando está disponible y degradan a memoria por proceso (misma
limitación documentada en rate limit/replay). Nunca se guarda PII: solo el
``sub`` opaco.
"""

from __future__ import annotations

import json
import time as _time
from dataclasses import dataclass, field
from typing import Any, Protocol

#: TTL de la marca de revocación: basta con cubrir la vida del access token
#: (15 min); tras ella el token ya no renueva sin volver a autenticar.
REVOCATION_TTL_SECONDS = 900


class RevocationBackend(Protocol):
    async def revoke(self, sub: str, reason: str, ttl: int) -> None: ...
    async def is_revoked(self, sub: str) -> bool: ...
    async def clear_revoked(self, sub: str) -> None: ...
    async def note_capabilities(self, sub: str, capabilities: list[str], ttl: int) -> None: ...
    async def get_capabilities(self, sub: str) -> list[str] | None: ...


class MemoryRevocationBackend:
    """Backend en memoria (desarrollo/pruebas; no distribuido)."""

    def __init__(self) -> None:
        self._revoked: dict[str, float] = {}
        self._caps: dict[str, tuple[list[str], float]] = {}

    def _purge(self, now: float) -> None:
        self._revoked = {k: v for k, v in self._revoked.items() if v > now}
        self._caps = {k: v for k, v in self._caps.items() if v[1] > now}

    async def revoke(self, sub: str, reason: str, ttl: int) -> None:
        now = _time.time()
        self._purge(now)
        self._revoked[sub] = now + ttl

    async def is_revoked(self, sub: str) -> bool:
        now = _time.time()
        self._purge(now)
        return sub in self._revoked

    async def clear_revoked(self, sub: str) -> None:
        now = _time.time()
        self._purge(now)
        self._revoked.pop(sub, None)

    async def note_capabilities(self, sub: str, capabilities: list[str], ttl: int) -> None:
        now = _time.time()
        self._purge(now)
        self._caps[sub] = (sorted(capabilities), now + ttl)

    async def get_capabilities(self, sub: str) -> list[str] | None:
        self._purge(_time.time())
        entry = self._caps.get(sub)
        return list(entry[0]) if entry else None


class RedisRevocationBackend:
    """Backend distribuido sobre Redis (misma semántica)."""

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._redis: Any = None

    async def _client(self) -> Any:
        if self._redis is None:
            import redis.asyncio as aioredis  # import perezoso

            self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._redis

    async def revoke(self, sub: str, reason: str, ttl: int) -> None:
        client = await self._client()
        await client.set(f"revoked:sub:{sub}", reason, ex=ttl)

    async def is_revoked(self, sub: str) -> bool:
        client = await self._client()
        return bool(await client.exists(f"revoked:sub:{sub}"))

    async def clear_revoked(self, sub: str) -> None:
        client = await self._client()
        await client.delete(f"revoked:sub:{sub}")

    async def note_capabilities(self, sub: str, capabilities: list[str], ttl: int) -> None:
        client = await self._client()
        await client.set(
            f"caps:sub:{sub}", json.dumps(sorted(capabilities)), ex=ttl
        )

    async def get_capabilities(self, sub: str) -> list[str] | None:
        client = await self._client()
        raw = await client.get(f"caps:sub:{sub}")
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except ValueError:
            return None
        return [str(c) for c in data] if isinstance(data, list) else None

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None


@dataclass
class _SessionState:
    capabilities: frozenset[str]
    opened_at: float = field(default_factory=_time.monotonic)


class ReauthRegistry:
    """Estado de las sesiones WSS activas por ``sub`` (para re-verificación)."""

    def __init__(self, backend: RevocationBackend) -> None:
        self._backend = backend
        self._local = MemoryRevocationBackend()
        self._sessions: dict[str, _SessionState] = {}

    async def _safe(self, method: str, *args: Any) -> None:
        """Invoca el backend distribuido tolerando su indisponibilidad."""
        try:
            await getattr(self._backend, method)(*args)
        except Exception:  # pragma: no cover - Redis caído ⇒ seguimos con local
            pass

    async def register(self, sub: str, capabilities: frozenset[str]) -> None:
        self._sessions[sub] = _SessionState(capabilities=capabilities)
        payload = sorted(capabilities)
        await self._safe("note_capabilities", sub, payload, REVOCATION_TTL_SECONDS)
        await self._local.note_capabilities(sub, payload, REVOCATION_TTL_SECONDS)

    def unregister(self, sub: str) -> None:
        self._sessions.pop(sub, None)

    async def clear_revoked(self, sub: str) -> None:
        """Desmarca la revocación del ``sub`` (p. ej. al autenticarse de nuevo)."""
        await self._safe("clear_revoked", sub)
        await self._local.clear_revoked(sub)

    async def recheck(self, sub: str, required_capability: str) -> str:
        """Devuelve ``ok`` / ``revoked`` / ``role_changed``.

        - ``revoked``: el ``sub`` está en la lista de revocación o perdió la
          capacidad requerida → cierre ``4003``.
        - ``role_changed``: las capacidades cambiaron pero el acceso sigue
          autorizado → cierre ``4403`` (re-autenticación ordenada).
        """
        revoked = await self._local.is_revoked(sub)
        remote: list[str] | None = None
        try:
            revoked = revoked or await self._backend.is_revoked(sub)
            remote = await self._backend.get_capabilities(sub)
        except Exception:  # pragma: no cover - degradación a local
            remote = None
        if revoked:
            return "revoked"
        if remote is None:
            remote = await self._local.get_capabilities(sub)
        session = self._sessions.get(sub)
        if remote is None or session is None:
            return "ok"
        remote_set = frozenset(remote)
        if required_capability not in remote_set:
            return "revoked"
        if remote_set != session.capabilities:
            return "role_changed"
        return "ok"

    async def mark_revoked(self, sub: str, reason: str = "role_revoked") -> None:
        """Marca un ``sub`` como revocado (p. ej. al retirar rol/desactivar)."""
        await self._safe("revoke", sub, reason, REVOCATION_TTL_SECONDS)
        await self._local.revoke(sub, reason, REVOCATION_TTL_SECONDS)

    async def set_capabilities(self, sub: str, capabilities: frozenset[str]) -> None:
        """Actualiza la instantánea de capacidades observada por el backend."""
        payload = sorted(capabilities)
        await self._safe("note_capabilities", sub, payload, REVOCATION_TTL_SECONDS)
        await self._local.note_capabilities(sub, payload, REVOCATION_TTL_SECONDS)


_registry: ReauthRegistry | None = None


def get_reauth_registry() -> ReauthRegistry:
    """Registro de re-verificación (singleton) según la configuración."""
    global _registry
    if _registry is None:
        from app.config import get_settings

        settings = get_settings()
        backend: RevocationBackend
        if settings.redis_url:
            backend = RedisRevocationBackend(settings.redis_url)
        else:
            backend = MemoryRevocationBackend()
        _registry = ReauthRegistry(backend)
    return _registry


async def close_reauth_registry() -> None:
    global _registry
    backend = getattr(_registry, "_backend", None)
    if backend is not None and hasattr(backend, "close"):
        await backend.close()
    _registry = None
