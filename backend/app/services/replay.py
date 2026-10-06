"""Anti-replay del webhook de Apps Script (spec §2.2.1, §10.5, RF-01.k, T24).

Cierra la cadena de autenticación del webhook (T23) con los dos chequeos de
frescura de ``§2.2.1`` que se ejecutan **antes de deserializar/persistir**:

- **``X-Webhook-Nonce`` de 128 bits** no visto en la ventana: caché Redis de
  ``replay_window_seconds`` (600 s) con ``SET NX EX`` (atómico), **namespaced por
  ``webhook_id``** para que dos orígenes no colisionen. Si el nonce ya existe →
  repetición → ``409`` (``ANTI_REPLAY``, §10.5).
- **``X-Webhook-Timestamp``** dentro de ±``replay_clock_skew_seconds`` (300 s)
  respecto al reloj autoritativo del backend → si está desalineado → ``409``.

Cada rechazo se **audita** (actor = ``webhook_id``, causa sin PII). El guard se
invoca desde ``authenticate_webhook`` (``app/services/auth.py``) reutilizando la
``WebhookIdentity`` ya verificada (``webhook_id``, ``nonce``, ``timestamp``), de
modo que nunca se acepta un nonce repetido ni un reloj desviado.

Base distribuida: Redis. Si Redis no está disponible se degrada a un conjunto
en memoria **por proceso** con la **misma ventana de 600 s** (no distribuido ni
compartido entre réplicas; limitación documentada, igual que
``app/core/rate_limit.py``). La degradación **nunca acepta en silencio**: se
registra un ``warning`` y el chequeo en memoria sigue rechazando repeticiones,
por lo que el fallo es cerrado respecto del anti-replay dentro del proceso.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import NoReturn, Protocol

import redis.asyncio as aioredis

from app.config import Settings, get_settings
from app.core.errors import raise_http_error
from app.core.logging import get_logger

logger = get_logger(__name__)

# Código de error uniforme para el anti-replay (409, spec §10.5).
ANTI_REPLAY_CODE = "ANTI_REPLAY"

# Razones auditables (sin PII): causa estable del rechazo.
REASON_NONCE_REPLAY = "nonce_replay"
REASON_TIMESTAMP_OUT_OF_WINDOW = "timestamp_out_of_window"
REASON_NONCE_MALFORMED = "nonce_malformed"

_NONCE_RE = re.compile(r"^[0-9a-fA-F]{32}$")
_NONCE_HEX_LEN = 32  # 128 bits


class ReplayIdentity(Protocol):
    """Contrato estructural mínimo que reutiliza ``WebhookIdentity`` (T23).

    Evita un import circular ``auth`` ↔ ``replay``: ``replay`` no conoce el tipo
    concreto, solo los tres campos verificados que necesitan leerse.
    """

    @property
    def webhook_id(self) -> str: ...

    @property
    def nonce(self) -> str: ...

    @property
    def timestamp(self) -> datetime: ...


@dataclass(frozen=True)
class ReplayResult:
    """Resultado del chequeo anti-replay para una identidad aceptada."""

    webhook_id: str
    nonce: str
    timestamp: datetime


def _as_utc(value: datetime) -> datetime:
    """Normaliza a UTC (asume UTC si el ``datetime`` viene sin zona)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _nonce_key(webhook_id: str, nonce: str) -> str:
    """Clave Redis namespaced por origen (evita colisiones entre webhooks)."""
    return f"replay:webhook:nonce:{webhook_id}:{nonce.lower()}"


class ReplayGuard:
    """Guarda anti-replay con base Redis (``SET NX EX``) y fallback en memoria."""

    def __init__(self, settings: Settings) -> None:
        self._redis_url = settings.redis_url
        self._redis: aioredis.Redis | None = None
        self._memory: dict[str, float] = {}
        self._window = settings.replay_window_seconds
        self._redis_healthy = bool(self._redis_url)
        self._retry_redis_at = 0.0
        if not self._redis_url:
            logger.warning(
                "replay_memory_only",
                extra={"event": "replay_fallback", "result": "no_redis_configured"},
            )

    async def _client(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
        return self._redis

    async def reserve(self, *, webhook_id: str, nonce: str) -> bool:
        """Reserva el nonce para ``webhook_id``.

        Devuelve ``True`` si es **nuevo** (aceptado) y ``False`` si ya fue visto
        en la ventana (repetición). Nunca acepta en silencio: si Redis falla se
        registra el fallback y se aplica la ventana en memoria del proceso.
        """
        key = _nonce_key(webhook_id, nonce)
        if self._redis_healthy and self._redis_url:
            try:
                client = await self._client()
                # SET NX EX: atómico. ``True`` = nuevo, ``None`` = ya existía.
                set_result = await client.set(key, "1", nx=True, ex=self._window)
                return bool(set_result)
            except Exception:
                logger.warning(
                    "replay_fallback",
                    extra={"event": "replay_fallback", "result": "redis_unavailable"},
                )
                self._redis_healthy = False
                self._retry_redis_at = time.monotonic() + 30.0
        elif (
            self._redis_url and not self._redis_healthy and time.monotonic() >= self._retry_redis_at
        ):
            # Reintenta Redis de forma periódica tras un fallo.
            self._redis_healthy = True

        return self._reserve_memory(key)

    def _reserve_memory(self, key: str) -> bool:
        """Fallback en memoria por proceso, respetando la ventana de 600 s."""
        now = time.monotonic()
        expiry = self._memory.get(key)
        if expiry is not None and expiry > now:
            return False
        if len(self._memory) > 100_000:
            # Purga de expirados antes de vaciar para no perder la ventana activa.
            self._memory = {k: v for k, v in self._memory.items() if v > now}
            if len(self._memory) > 100_000:
                self._memory.clear()
        self._memory[key] = now + self._window
        return True

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None


_guard: ReplayGuard | None = None


def get_replay_guard() -> ReplayGuard:
    """Devuelve (creando si hace falta) el guard anti-replay del proceso."""
    global _guard
    if _guard is None:
        _guard = ReplayGuard(get_settings())
    return _guard


async def close_replay_guard() -> None:
    """Cierra el guard anti-replay (``lifespan`` de la app)."""
    global _guard
    if _guard is not None:
        await _guard.close()
        _guard = None


def _client_ip(request: object | None) -> str:
    client = getattr(request, "client", None)
    return getattr(client, "host", "") if client is not None else ""


def _user_agent(request: object | None) -> str:
    headers = getattr(request, "headers", None)
    if headers is None:
        return ""
    try:
        return str(headers.get("User-Agent", "") or "")
    except Exception:  # pragma: no cover - cabeceras no mapeables
        return ""


async def _audit_rejection(
    *,
    webhook_id: str,
    reason: str,
    request: object | None,
    session: object | None,
) -> None:
    """Audita un rechazo anti-replay sin que su fallo enmascare el ``409``.

    Se importa ``record_audit`` de forma diferida para no acoplar el módulo de
    replay a la capa de persistencia y permitir dobles en pruebas unitarias.
    """
    try:
        from app.services.audit import record_audit

        await record_audit(
            actor=webhook_id or "unknown",
            action="webhook.rejected",
            resource=f"anti_replay:{reason}",
            result="rejected",
            ip=_client_ip(request),
            user_agent=_user_agent(request),
            session=session,  # type: ignore[arg-type]
        )
    except Exception:
        logger.warning(
            "replay_audit_failed",
            extra={"event": "replay_audit", "result": "error"},
        )


async def _reject(
    *,
    webhook_id: str,
    reason: str,
    message: str,
    request: object | None,
    session: object | None,
) -> NoReturn:
    """Audita el intento y responde ``409`` (``ANTI_REPLAY``)."""
    await _audit_rejection(webhook_id=webhook_id, reason=reason, request=request, session=session)
    raise_http_error(ANTI_REPLAY_CODE, message)


async def enforce_replay(
    identity: ReplayIdentity,
    *,
    request: object | None = None,
    session: object | None = None,
    now: datetime | None = None,
    guard: ReplayGuard | None = None,
) -> ReplayResult:
    """Aplica las dos comprobaciones de frescura del anti-replay (T24).

    Orden (spec §2.2.1 pasos 5 y 6): primero la ventana temporal (±300 s) y
    después el cache de nonce (600 s). Cualquier fallo corta con ``409`` y se
    audita. Se invoca tras verificar la firma (T23) y **antes** de interpretar
    el cuerpo.
    """
    settings = get_settings()

    # 5. Desalineación temporal dentro de ±300 s → 409 (RF-01.k).
    momento = _as_utc(now) if now is not None else datetime.now(timezone.utc)
    if not _NONCE_RE.match(identity.nonce or "") or len(identity.nonce) != _NONCE_HEX_LEN:
        await _reject(
            webhook_id=identity.webhook_id,
            reason=REASON_NONCE_MALFORMED,
            message="Anti-replay: nonce malformado (128 bits hex esperados).",
            request=request,
            session=session,
        )
    skew_seconds = abs((momento - _as_utc(identity.timestamp)).total_seconds())
    if skew_seconds > settings.replay_clock_skew_seconds:
        await _reject(
            webhook_id=identity.webhook_id,
            reason=REASON_TIMESTAMP_OUT_OF_WINDOW,
            message="Anti-replay: timestamp fuera de la ventana temporal (±300 s).",
            request=request,
            session=session,
        )

    # 6. Nonce no visto en la ventana de replay (cache 600 s) → 409.
    active_guard = guard if guard is not None else get_replay_guard()
    if not await active_guard.reserve(webhook_id=identity.webhook_id, nonce=identity.nonce):
        await _reject(
            webhook_id=identity.webhook_id,
            reason=REASON_NONCE_REPLAY,
            message="Anti-replay: nonce ya visto en la ventana (repetición detectada).",
            request=request,
            session=session,
        )

    return ReplayResult(
        webhook_id=identity.webhook_id,
        nonce=identity.nonce,
        timestamp=_as_utc(identity.timestamp),
    )
