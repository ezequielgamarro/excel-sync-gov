"""Test unitario del bus de distribución (T28, spec §3.3/§7.2, RNF-04.d/RNF-06.c).

Cubre, con un **Redis simulado** (cliente inyectado), lo esencial de T28:

- ``seq`` **monótono por sala** asignado de forma atómica (``INCR``): nunca
  decrece ni se repite, y no se cruza entre salas.
- El ``seq`` persistido por la ingesta (suelo) mantiene la consistencia con el
  cold start: el contador Redis no queda por debajo.
- Fan-out por ``room_id``: la clave del canal es ``room:{room_id}``.
- Presencia/conteo de conexiones por sala en Redis (§3.3).
- Degradación: sin Redis configurado, el bus no rompe y devuelve ``None``.

En entornos sin dependencias (redis/sqlalchemy/pydantic) el cargador instala
*stubs* mínimos (mismo enfoque que ``test_ingest_webhook.py``). Se puede ejecutar
con pytest o directamente::

    py backend/tests/test_bus.py
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
def _install_stubs() -> None:
    for name, path in (
        ("app", _BACKEND / "app"),
        ("app.core", _BACKEND / "app" / "core"),
        ("app.services", _BACKEND / "app" / "services"),
    ):
        pkg = types.ModuleType(name)
        pkg.__path__ = [str(path)]
        sys.modules.setdefault(name, pkg)

    logging_mod = types.ModuleType("app.core.logging")
    logging_mod.get_logger = logging.getLogger  # type: ignore[attr-defined]
    sys.modules["app.core.logging"] = logging_mod

    config_mod = types.ModuleType("app.config")

    class _Settings:
        redis_url = ""

    config_mod.Settings = _Settings  # type: ignore[attr-defined]
    config_mod.get_settings = lambda: _Settings()  # type: ignore[attr-defined]
    sys.modules["app.config"] = config_mod

    aggregate_mod = types.ModuleType("app.services.aggregate")

    async def _enrich_payload(_session: Any, payload: Any, **_kwargs: Any) -> Any:
        return payload

    aggregate_mod.enrich_payload = _enrich_payload  # type: ignore[attr-defined]
    sys.modules["app.services.aggregate"] = aggregate_mod

    sqlalchemy_mod = types.ModuleType("sqlalchemy")
    ext_mod = types.ModuleType("sqlalchemy.ext")
    asyncio_mod = types.ModuleType("sqlalchemy.ext.asyncio")

    class _AsyncSession:
        pass

    asyncio_mod.AsyncSession = _AsyncSession  # type: ignore[attr-defined]
    sys.modules["sqlalchemy"] = sqlalchemy_mod
    sys.modules["sqlalchemy.ext"] = ext_mod
    sys.modules["sqlalchemy.ext.asyncio"] = asyncio_mod

    redis_mod = types.ModuleType("redis")
    redis_asyncio_mod = types.ModuleType("redis.asyncio")

    class _Redis:
        pass

    redis_asyncio_mod.Redis = _Redis  # type: ignore[attr-defined]
    redis_asyncio_mod.from_url = lambda *a, **k: _Redis()  # type: ignore[attr-defined]
    redis_mod.asyncio = redis_asyncio_mod  # type: ignore[attr-defined]
    sys.modules["redis"] = redis_mod
    sys.modules["redis.asyncio"] = redis_asyncio_mod


def _load_module(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_bus() -> types.ModuleType:
    try:
        import redis  # noqa: F401
        import sqlalchemy  # noqa: F401
        from app.services import bus

        return bus
    except ImportError:
        _install_stubs()
        return _load_module("app.services.bus", _BACKEND / "app" / "services" / "bus.py")


bus = _load_bus()


# =============================================================================
# Redis simulado
# =============================================================================
class _FakeRedis:
    """Doble en memoria de la superficie Redis usada por ``RoomBus``."""

    def __init__(self) -> None:
        self.kv: dict[str, int] = {}
        self.sets: dict[str, set[str]] = {}
        self.published: list[tuple[str, str]] = []
        self.healthy = True

    async def incr(self, key: str) -> int:
        self.kv[key] = self.kv.get(key, 0) + 1
        return self.kv[key]

    async def get(self, key: str) -> str | None:
        value = self.kv.get(key)
        return None if value is None else str(value)

    async def set(self, key: str, value: Any) -> bool:
        self.kv[key] = int(value)
        return True

    async def sadd(self, key: str, member: str) -> int:
        self.sets.setdefault(key, set()).add(member)
        return 1

    async def srem(self, key: str, member: str) -> int:
        self.sets.get(key, set()).discard(member)
        return 1

    async def scard(self, key: str) -> int:
        return len(self.sets.get(key, set()))

    async def publish(self, channel: str, data: str) -> int:
        self.published.append((channel, data))
        return 1

    async def aclose(self) -> None:  # pragma: no cover - el bus no cierra clientes inyectados
        return None


class _Settings:
    redis_url = "redis://test/0"


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _bus(client: _FakeRedis) -> Any:
    return bus.RoomBus(_Settings(), client=client)


# =============================================================================
# Casos
# =============================================================================
def test_seq_is_monotonic_per_room() -> None:
    fake = _FakeRedis()
    room = _bus(fake)

    seqs = [_run(room.next_seq("sala-central")) for _ in range(3)]
    assert seqs == [1, 2, 3]

    # Otra sala mantiene su propio contador (no se cruzan).
    assert _run(room.next_seq("sala-sur")) == 1
    assert _run(room.next_seq("sala-central")) == 4


def test_seq_floor_matches_persisted_seq() -> None:
    fake = _FakeRedis()
    room = _bus(fake)

    # El seq de BD (F3/T26) actúa de suelo para no romper el cold start.
    assert _run(room.next_seq("sala-central", floor=10427)) == 10427
    assert _run(room.next_seq("sala-central")) == 10428
    assert _run(room.get_last_seq("sala-central")) == 10428


def test_publish_uses_room_channel() -> None:
    fake = _FakeRedis()
    room = _bus(fake)

    ok = _run(room.publish("sala-central", {"seq": 1, "type": "indicators.snapshot"}))
    assert ok is True
    assert fake.published
    channel, data = fake.published[0]
    assert channel == "room:sala-central"
    assert '"seq":1' in data


def test_presence_counts_connections_per_room() -> None:
    fake = _FakeRedis()
    room = _bus(fake)

    assert _run(room.register_connection("sala-central", "conn-1")) == 1
    assert _run(room.register_connection("sala-central", "conn-2")) == 2
    assert _run(room.register_connection("sala-sur", "conn-3")) == 1
    assert _run(room.connection_count("sala-central")) == 2
    assert _run(room.unregister_connection("sala-central", "conn-1")) == 1


def test_degraded_without_redis_returns_none() -> None:
    class _NoRedisSettings:
        redis_url = ""

    room = bus.RoomBus(_NoRedisSettings())
    assert room._redis_healthy is False

    assert _run(room.next_seq("sala-central")) is None
    assert _run(room.get_last_seq("sala-central")) is None
    assert _run(room.register_connection("sala-central", "conn-1")) is None


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
