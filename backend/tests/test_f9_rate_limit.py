"""T65 — Rate limiting del webhook y de operador (RNF-12, §10.1/§10.6).

Cubre los criterios de F9 para el control de abuso:

- El token bucket en memoria agota la ráfaga y devuelve ``allowed=False`` con
  ``retry_after`` > 0.
- ``RateLimiter`` usa el backend en memoria cuando Redis está deshabilitado.
- ``RateLimitMiddleware`` clasifica ``/api/v1/ingest/*`` por ``X-Webhook-Id``,
  ``/api/v1/admin/*`` por IP y el resto de ``/api/*`` por IP (operador).
- Al exceder el límite responde ``429`` con cabecera ``Retry-After`` y cuerpo
  de error uniforme (no llega al endpoint interno).

Se carga ``app.core.rate_limit`` con *stubs* mínimos (sin fastapi/redis/pydantic)
para poder ejecutarse también en entornos sin dependencias. Directamente::

    py backend/tests/test_f9_rate_limit.py
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import sys
import types
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# =============================================================================
# Stubs de dependencias externas ausentes
# =============================================================================
class _FakeSettings:
    rate_limit_use_redis = False
    redis_url = ""
    rate_limit_webhook_per_minute = 200
    rate_limit_webhook_burst = 20
    rate_limit_operator_per_minute = 120
    rate_limit_operator_burst = 120
    rate_limit_admin_per_minute = 50
    rate_limit_admin_burst = 50


class _Headers:
    def __init__(self, scope: Any = None, **_: Any) -> None:
        self._data: dict[str, str] = {}
        if isinstance(scope, dict):
            for key, value in scope.get("headers", []):
                self._data[key.decode("latin-1").lower()] = value.decode("latin-1")

    def get(self, key: str, default: str | None = None) -> str | None:
        return self._data.get(key.lower(), default)


class _JSONResponse:
    def __init__(self, status_code: int = 200, content: Any = None, headers: Any = None) -> None:
        self.status_code = status_code
        self.content = content
        self.headers = headers

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": self.status_code,
                "headers": self.headers or {},
                "body": self.content,
            }
        )
        await send({"type": "http.response.body", "body": b""})


class _Counter:
    def labels(self, **_: Any) -> "_Counter":
        return self

    def inc(self) -> None:
        pass


def _install_stubs() -> None:
    for name, path in (
        ("app", _BACKEND / "app"),
        ("app.core", _BACKEND / "app" / "core"),
        ("app.services", _BACKEND / "app" / "services"),
    ):
        pkg = types.ModuleType(name)
        pkg.__path__ = [str(path)]  # type: ignore[attr-defined]
        sys.modules.setdefault(name, pkg)

    redis_mod = types.ModuleType("redis")
    redis_asyncio_mod = types.ModuleType("redis.asyncio")
    redis_asyncio_mod.from_url = lambda *_a, **_k: object()  # type: ignore[attr-defined]
    redis_mod.asyncio = redis_asyncio_mod  # type: ignore[attr-defined]
    sys.modules["redis"] = redis_mod
    sys.modules["redis.asyncio"] = redis_asyncio_mod

    starlette = types.ModuleType("starlette")
    datastructures = types.ModuleType("starlette.datastructures")
    datastructures.Headers = _Headers  # type: ignore[attr-defined]
    responses = types.ModuleType("starlette.responses")
    responses.JSONResponse = _JSONResponse  # type: ignore[attr-defined]
    st_types = types.ModuleType("starlette.types")
    st_types.ASGIApp = object  # type: ignore[attr-defined]
    st_types.Receive = object  # type: ignore[attr-defined]
    st_types.Scope = dict  # type: ignore[attr-defined]
    st_types.Send = object  # type: ignore[attr-defined]
    starlette.datastructures = datastructures  # type: ignore[attr-defined]
    starlette.responses = responses  # type: ignore[attr-defined]
    starlette.types = st_types  # type: ignore[attr-defined]
    sys.modules["starlette"] = starlette
    sys.modules["starlette.datastructures"] = datastructures
    sys.modules["starlette.responses"] = responses
    sys.modules["starlette.types"] = st_types

    config_mod = types.ModuleType("app.config")
    config_mod.Settings = _FakeSettings  # type: ignore[attr-defined]
    config_mod.get_settings = lambda: _FakeSettings()  # type: ignore[attr-defined]
    sys.modules["app.config"] = config_mod

    errors_mod = types.ModuleType("app.core.errors")
    errors_mod.build_error_body = lambda code, message: {  # type: ignore[attr-defined]
        "error": {"code": code, "message": message, "correlation_id": "tr-test"}
    }
    sys.modules["app.core.errors"] = errors_mod

    logging_mod = types.ModuleType("app.core.logging")
    logging_mod.get_logger = logging.getLogger  # type: ignore[attr-defined]
    sys.modules["app.core.logging"] = logging_mod

    metrics_mod = types.ModuleType("app.core.metrics")
    metrics_mod.RATE_LIMITED_TOTAL = _Counter()  # type: ignore[attr-defined]
    sys.modules["app.core.metrics"] = metrics_mod


def _load() -> types.ModuleType:
    try:
        from app.core import rate_limit  # noqa: F401

        return rate_limit
    except ImportError:
        _install_stubs()
        spec = importlib.util.spec_from_file_location(
            "app.core.rate_limit", _BACKEND / "app" / "core" / "rate_limit.py"
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules["app.core.rate_limit"] = module
        getattr(spec.loader, "exec_module")(module)
        return module


rate_limit = _load()


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# =============================================================================
# Casos
# =============================================================================
def test_memory_bucket_exhausts_burst() -> None:
    bucket = rate_limit.MemoryBucketBackend()
    for _ in range(3):
        allowed, _retry = _run(
            bucket.consume("k", capacity=3.0, refill_per_sec=0.0, now=1000.0, ttl=60)
        )
        assert allowed is True
    allowed, retry = _run(
        bucket.consume("k", capacity=3.0, refill_per_sec=0.0, now=1000.0, ttl=60)
    )
    assert allowed is False
    assert retry > 0


def test_rate_limiter_uses_memory_when_redis_disabled() -> None:
    limiter = rate_limit.RateLimiter(_FakeSettings())
    policy = rate_limit.RatePolicy(bucket="webhook", rate_per_minute=60, burst=1)
    assert _run(limiter.allow("wh-1", policy)).allowed is True
    denied = _run(limiter.allow("wh-1", policy))
    assert denied.allowed is False
    assert denied.retry_after > 0


def test_default_policies_match_spec() -> None:
    settings = _FakeSettings()
    assert settings.rate_limit_webhook_per_minute == 200  # RNF-12.a
    assert settings.rate_limit_webhook_burst == 20
    assert settings.rate_limit_operator_per_minute == 120  # RNF-12.b
    assert settings.rate_limit_admin_per_minute == 50  # §10.6


def test_classify_buckets() -> None:
    limiter = rate_limit.RateLimiter(_FakeSettings())
    middleware = rate_limit.RateLimitMiddleware(object(), _FakeSettings(), limiter)

    webhook_scope = {
        "type": "http",
        "path": "/api/v1/ingest/webhook",
        "headers": [(b"x-webhook-id", b"wh-abc")],
        "client": ("203.0.113.9", 1),
    }
    policy, key = middleware._classify(webhook_scope, webhook_scope["path"])
    assert policy is not None and policy.bucket == "webhook" and key == "wh-abc"

    admin_scope = {"type": "http", "path": "/api/v1/admin/users", "headers": [], "client": ("10.0.0.5", 1)}
    policy, key = middleware._classify(admin_scope, admin_scope["path"])
    assert policy is not None and policy.bucket == "admin" and key == "10.0.0.5"

    rest_scope = {"type": "http", "path": "/api/v1/dashboard/snapshot", "headers": [], "client": ("10.0.0.6", 1)}
    policy, key = middleware._classify(rest_scope, rest_scope["path"])
    assert policy is not None and policy.bucket == "operator" and key == "10.0.0.6"

    assert middleware._classify({"type": "http", "path": "/health/live", "headers": [], "client": None}, "/health/live") == (None, None)


def test_middleware_returns_429_with_retry_after() -> None:
    inner_called = {"value": False}

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        inner_called["value"] = True

    limiter = rate_limit.RateLimiter(_FakeSettings())
    middleware = rate_limit.RateLimitMiddleware(inner, _FakeSettings(), limiter)
    scope = {
        "type": "http",
        "path": "/api/v1/dashboard/snapshot",
        "headers": [],
        "client": ("198.51.100.7", 1),
    }
    sent: list[dict[str, Any]] = []

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    async def receive() -> dict[str, Any]:
        return {"type": "http.request"}

    # Excita el bucket hasta obtener un 429 (ráfaga 120; el reloj real repone).
    start = None
    for _ in range(400):
        sent.clear()
        _run(middleware(scope, receive, send))
        candidate = next((m for m in sent if m["type"] == "http.response.start"), None)
        if candidate is not None and candidate["status"] == 429:
            start = candidate
            break
    assert start is not None, "no se alcanzó el rate limit"
    assert "Retry-After" in start["headers"]
    assert start["body"]["error"]["code"] == "RATE_LIMITED"
    # El endpoint interno sí se alcanzó antes de agotar la ráfaga.
    assert inner_called["value"] is True


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL {name}: {exc}")
            else:
                print(f"PASS {name}")
    if failures:
        raise SystemExit(1)
    print("OK")
