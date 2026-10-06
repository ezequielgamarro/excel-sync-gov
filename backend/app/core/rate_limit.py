"""Rate limiting base (spec RNF-12, §10.1/§10.6).

Política (configurable por entorno):

- **Webhook del origen** (``/api/v1/ingest/*``):
  ``rate_limit_webhook_per_minute`` req/min, ráfaga ``rate_limit_webhook_burst``,
  clave = ``webhook_id`` (cabecera ``X-Webhook-Id``).
- **Operador** (resto de ``/api/*``): ``rate_limit_operator_per_minute`` req/min,
  clave = ``sub`` (extraído del JWT nativo verificado; el middleware RBAC/rate
  limit aún no lo conoce, así que degrada a la IP del socket).
- **Admin** (``/api/v1/admin/*``): 50 req/min por ``sub`` (spec §10.6).

Base distribuida: Redis (token bucket con script Lua atómico). Si Redis no está
disponible (o ``rate_limit_use_redis=false``), degrada a un bucket en memoria
por proceso — **no distribuido**: con varias réplicas el límite efectivo se
multiplica por el número de réplicas. Exceder el límite devuelve ``429`` con
``Retry-After`` y cuerpo de error uniforme. Los endpoints ``/health/*``,
``/metrics`` y ``/schema/*`` no se limitan.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Final

import redis.asyncio as aioredis
from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from app.config import Settings
from app.core.errors import build_error_body
from app.core.logging import get_logger
from app.core.metrics import RATE_LIMITED_TOTAL

logger = get_logger(__name__)

_TOKEN_BUCKET_LUA: Final = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local ttl = tonumber(ARGV[4])

local tokens = capacity
local last = now
local current = redis.call('HMGET', key, 'tokens', 'ts')
if current[1] ~= false then
    tokens = tonumber(current[1])
    last = tonumber(current[2])
end

local elapsed = math.max(0, now - last)
tokens = math.min(capacity, tokens + elapsed * refill)

local allowed = 0
local retry_after = 0
if tokens >= 1 then
    tokens = tokens - 1
    allowed = 1
else
    retry_after = math.ceil((1 - tokens) / refill)
end

redis.call('HSET', key, 'tokens', tokens, 'ts', now)
redis.call('EXPIRE', key, ttl)

return {allowed, retry_after}
"""


@dataclass(frozen=True)
class RatePolicy:
    """Política de rate limiting para un bucket."""

    bucket: str
    rate_per_minute: int
    burst: int


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after: float


class MemoryBucketBackend:
    """Token bucket en memoria por proceso (fallback sin Redis)."""

    def __init__(self, max_entries: int = 10_000) -> None:
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = asyncio.Lock()
        self._max_entries = max_entries

    async def consume(
        self,
        key: str,
        *,
        capacity: float,
        refill_per_sec: float,
        now: float,
        ttl: int,
    ) -> tuple[bool, float]:
        async with self._lock:
            tokens, last = self._buckets.get(key, (capacity, now))
            elapsed = max(0.0, now - last)
            tokens = min(capacity, tokens + elapsed * refill_per_sec)
            if tokens >= 1.0:
                tokens -= 1.0
                self._buckets[key] = (tokens, now)
                return True, 0.0
            retry_after = (1.0 - tokens) / refill_per_sec if refill_per_sec > 0 else 1.0
            self._buckets[key] = (tokens, now)
            if len(self._buckets) > self._max_entries:
                self._buckets.clear()
            return False, retry_after


class RedisBucketBackend:
    """Token bucket distribuido sobre Redis (script Lua atómico)."""

    def __init__(self, redis_url: str) -> None:
        self._redis_url = redis_url
        self._redis: aioredis.Redis | None = None

    async def _client(self) -> aioredis.Redis:
        if self._redis is None:
            self._redis = aioredis.from_url(self._redis_url, decode_responses=False)
        return self._redis

    async def consume(
        self,
        key: str,
        *,
        capacity: float,
        refill_per_sec: float,
        now: float,
        ttl: int,
    ) -> tuple[bool, float]:
        client = await self._client()
        result = await client.eval(
            _TOKEN_BUCKET_LUA,
            1,
            key,
            str(capacity),
            str(refill_per_sec),
            str(now),
            str(ttl),
        )
        return bool(int(result[0])), float(result[1])

    async def close(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None


class RateLimiter:
    """Aplica políticas de rate limit con base Redis y fallback a memoria."""

    def __init__(self, settings: Settings) -> None:
        self._redis_backend: RedisBucketBackend | None = None
        if settings.rate_limit_use_redis and settings.redis_url:
            self._redis_backend = RedisBucketBackend(settings.redis_url)
        self._memory = MemoryBucketBackend()
        self._redis_healthy = self._redis_backend is not None
        self._retry_redis_at = 0.0

    async def allow(self, key: str, policy: RatePolicy) -> RateLimitDecision:
        refill_per_sec = policy.rate_per_minute / 60.0
        now = time.time()
        ttl = max(60, int(policy.rate_per_minute * 1.5))

        if self._redis_backend is not None and self._redis_healthy:
            try:
                allowed, retry_after = await self._redis_backend.consume(
                    key=f"rl:{policy.bucket}:{key}",
                    capacity=float(policy.burst),
                    refill_per_sec=refill_per_sec,
                    now=now,
                    ttl=ttl,
                )
                return RateLimitDecision(allowed=allowed, retry_after=retry_after)
            except Exception:
                logger.warning(
                    "rate_limit_fallback",
                    extra={"event": "rate_limit_fallback", "result": "redis_unavailable"},
                )
                self._redis_healthy = False
                self._retry_redis_at = now + 30.0
        elif self._redis_backend is not None and now >= self._retry_redis_at:
            # Reintenta Redis de forma periódica tras un fallo.
            self._redis_healthy = True

        allowed, retry_after = await self._memory.consume(
            key=f"{policy.bucket}:{key}",
            capacity=float(policy.burst),
            refill_per_sec=refill_per_sec,
            now=now,
            ttl=ttl,
        )
        return RateLimitDecision(allowed=allowed, retry_after=retry_after)

    async def close(self) -> None:
        if self._redis_backend is not None:
            await self._redis_backend.close()


class RateLimitMiddleware:
    """Clasifica cada petición en un bucket y aplica el rate limit correspondiente."""

    def __init__(self, app: ASGIApp, settings: Settings, limiter: RateLimiter) -> None:
        self.app = app
        self._settings = settings
        self._limiter = limiter

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        policy, key = self._classify(scope, path)
        if policy is None or key is None:
            await self.app(scope, receive, send)
            return

        decision = await self._limiter.allow(key, policy)
        if decision.allowed:
            await self.app(scope, receive, send)
            return

        RATE_LIMITED_TOTAL.labels(bucket=policy.bucket).inc()
        retry_after = max(1, int(round(decision.retry_after)))
        response = JSONResponse(
            status_code=429,
            content=build_error_body(
                "RATE_LIMITED",
                "Demasiadas solicitudes; reintente más tarde.",
            ),
            headers={"Retry-After": str(retry_after)},
        )
        await response(scope, receive, send)

    def _classify(self, scope: Scope, path: str) -> tuple[RatePolicy | None, str | None]:
        headers = Headers(scope=scope)
        if path.startswith("/api/v1/ingest/"):
            webhook_id = (headers.get("X-Webhook-Id") or "").strip() or self._ip(scope)
            return (
                RatePolicy(
                    bucket="webhook",
                    rate_per_minute=self._settings.rate_limit_webhook_per_minute,
                    burst=self._settings.rate_limit_webhook_burst,
                ),
                webhook_id,
            )
        if path.startswith("/api/v1/admin/"):
            return (
                RatePolicy(
                    bucket="admin",
                    rate_per_minute=self._settings.rate_limit_admin_per_minute,
                    burst=self._settings.rate_limit_admin_burst,
                ),
                self._ip(scope),
            )
        if path.startswith("/api/"):
            return (
                RatePolicy(
                    bucket="operator",
                    rate_per_minute=self._settings.rate_limit_operator_per_minute,
                    burst=self._settings.rate_limit_operator_burst,
                ),
                self._ip(scope),
            )
        return None, None

    def _ip(self, scope: Scope) -> str:
        client = scope.get("client")
        if client is not None and len(client) > 0:
            return str(client[0])
        return "unknown"
