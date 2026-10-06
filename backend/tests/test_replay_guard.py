"""Test unitario del guard anti-replay del webhook (T24, spec §2.2.1, §10.5).

Ejercita ``ReplayGuard`` y ``enforce_replay`` con un **stub de Redis** y una
auditoría en memoria:

- nonce nuevo → aceptado (``SET NX EX``);
- nonce repetido → ``409`` (``ANTI_REPLAY``) + auditoría del intento;
- mismo nonce de otro ``webhook_id`` → keyspace separado (no colisiona);
- timestamp fuera de ±300 s → ``409``.

Se puede ejecutar con pytest o directamente::

    py backend/tests/test_replay_guard.py
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_WEBHOOK_ID = "01924f3a-1c2b-7def-8a01-000000000001"
_OTHER_WEBHOOK_ID = "01924f3a-1c2b-7def-8a01-000000000002"
_NONCE = "7f3c9a2b1d8e4c6f5a0b3d9e8c7f6a1b"
_NOW = datetime(2026, 10, 3, 14, 22, 5, tzinfo=timezone.utc)


class _FakeRedis:
    """Stub mínimo de Redis: ``SET key value NX EX``."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.calls: list[tuple[str, bool, int | None]] = []

    async def set(self, key: str, value: str, *, nx: bool = False, ex: int | None = None) -> Any:
        self.calls.append((key, nx, ex))
        if nx and key in self.store:
            return None
        self.store[key] = value
        return True

    async def aclose(self) -> None:  # pragma: no cover - cierre
        return None


class _FakeSettings:
    redis_url = "redis://fake:6379/0"
    replay_window_seconds = 600
    replay_clock_skew_seconds = 300


def _install_stubs() -> None:
    for name, path in (
        ("app", _BACKEND / "app"),
        ("app.core", _BACKEND / "app" / "core"),
        ("app.services", _BACKEND / "app" / "services"),
    ):
        pkg = types.ModuleType(name)
        pkg.__path__ = [str(path)]  # type: ignore[attr-defined]
        sys.modules.setdefault(name, pkg)

    config_mod = types.ModuleType("app.config")
    config_mod.Settings = _FakeSettings  # type: ignore[attr-defined]
    config_mod.get_settings = lambda: _FakeSettings()  # type: ignore[attr-defined]
    sys.modules["app.config"] = config_mod

    class _StubAPIError(Exception):
        def __init__(self, status_code: int, code: str, message: str) -> None:
            super().__init__(message)
            self.status_code = status_code
            self.code = code
            self.message = message

    _status = {"ANTI_REPLAY": 409}

    def _raise(code: str, message: str, *, status_code: int | None = None) -> Any:
        raise _StubAPIError(status_code or _status.get(code, 500), code, message)

    errors_mod = types.ModuleType("app.core.errors")
    errors_mod.APIError = _StubAPIError  # type: ignore[attr-defined]
    errors_mod.raise_http_error = _raise  # type: ignore[attr-defined]
    sys.modules["app.core.errors"] = errors_mod

    logging_mod = types.ModuleType("app.core.logging")
    logging_mod.get_logger = logging.getLogger  # type: ignore[attr-defined]
    sys.modules["app.core.logging"] = logging_mod

    redis_mod = types.ModuleType("redis")
    redis_asyncio_mod = types.ModuleType("redis.asyncio")
    redis_asyncio_mod.from_url = lambda *_a, **_k: _FakeRedis()  # type: ignore[attr-defined]
    redis_mod.asyncio = redis_asyncio_mod  # type: ignore[attr-defined]
    sys.modules["redis"] = redis_mod
    sys.modules["redis.asyncio"] = redis_asyncio_mod

    audit_mod = types.ModuleType("app.services.audit")
    calls: list[dict[str, Any]] = []

    async def _record_audit(**kwargs: Any) -> None:
        calls.append(kwargs)

    audit_mod.record_audit = _record_audit  # type: ignore[attr-defined]
    audit_mod.calls = calls  # type: ignore[attr-defined]
    sys.modules["app.services.audit"] = audit_mod


def _load_replay() -> types.ModuleType:
    try:
        from app.services import replay  # noqa: F401

        return replay
    except ImportError:
        _install_stubs()
        spec = importlib.util.spec_from_file_location(
            "app.services.replay", _BACKEND / "app" / "services" / "replay.py"
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules["app.services.replay"] = module
        getattr(spec.loader, "exec_module")(module)
        return module


replay = _load_replay()
audit = sys.modules["app.services.audit"]


def _guard_with_fake_redis() -> tuple[Any, _FakeRedis]:
    guard = replay.ReplayGuard(_FakeSettings())
    fake = _FakeRedis()
    guard._redis = fake  # type: ignore[attr-defined]
    guard._redis_healthy = True  # type: ignore[attr-defined]
    return guard, fake


def _identity(
    nonce: str = _NONCE, webhook_id: str = _WEBHOOK_ID, timestamp: datetime = _NOW
) -> Any:
    return types.SimpleNamespace(webhook_id=webhook_id, nonce=nonce, timestamp=timestamp)


def _request() -> Any:
    return types.SimpleNamespace(
        headers={"User-Agent": "pytest"},
        client=types.SimpleNamespace(host="203.0.113.10"),
    )


def _enforce(identity: Any, guard: Any, *, now: datetime = _NOW) -> Any:
    return asyncio.run(
        replay.enforce_replay(
            identity,
            request=_request(),
            session=object(),
            now=now,
            guard=guard,
        )
    )


def _expect_reject(callable_: Any) -> Any:
    try:
        callable_()
    except Exception as exc:  # noqa: BLE001 - se inspecciona el código de rechazo
        return exc
    raise AssertionError("se esperaba un rechazo (409) y no ocurrió")


def test_new_nonce_accepted_and_replay_rejected() -> None:
    guard, fake = _guard_with_fake_redis()
    audit.calls.clear()  # type: ignore[attr-defined]
    result = _enforce(_identity(), guard)
    assert result.nonce == _NONCE
    assert fake.calls and fake.calls[0][1] is True and fake.calls[0][2] == 600
    exc = _expect_reject(lambda: _enforce(_identity(), guard))
    assert getattr(exc, "code", "") == "ANTI_REPLAY"
    assert getattr(exc, "status_code", 0) == 409
    assert audit.calls and audit.calls[-1]["resource"] == "anti_replay:nonce_replay"


def test_same_nonce_across_webhooks_does_not_collide() -> None:
    guard, _ = _guard_with_fake_redis()
    _enforce(_identity(), guard)
    # Otro origen con el mismo nonce debe seguir siendo aceptado (namespaced).
    result = _enforce(_identity(webhook_id=_OTHER_WEBHOOK_ID), guard)
    assert result.webhook_id == _OTHER_WEBHOOK_ID


def test_timestamp_out_of_window_rejected() -> None:
    guard, _ = _guard_with_fake_redis()
    audit.calls.clear()  # type: ignore[attr-defined]
    stale = _NOW - timedelta(minutes=10)
    exc = _expect_reject(lambda: _enforce(_identity(timestamp=stale), guard))
    assert getattr(exc, "code", "") == "ANTI_REPLAY"
    assert getattr(exc, "status_code", 0) == 409
    assert audit.calls and audit.calls[-1]["resource"] == "anti_replay:timestamp_out_of_window"


def test_memory_fallback_still_rejects_replay() -> None:
    settings = _FakeSettings()
    settings.redis_url = ""  # type: ignore[misc]
    guard = replay.ReplayGuard(settings)
    assert asyncio.run(guard.reserve(webhook_id=_WEBHOOK_ID, nonce=_NONCE)) is True
    assert asyncio.run(guard.reserve(webhook_id=_WEBHOOK_ID, nonce=_NONCE)) is False


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
