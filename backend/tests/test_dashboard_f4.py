"""Tests unitarios mínimos de F4 (T29 ticket WSS y T33 variación "vs ayer").

Verifican los contratos más propensos a error sin requerir dependencias externas
(el cargador instala *stubs* mínimos de ``redis``/``sqlalchemy``, mismo enfoque
que ``test_bus.py``):

- **T29**: el ticket WSS es de un solo uso y encarna ``sub`` + capacidades +
  ``room_id``; su redención consume el ticket (fail-closed ante reuso).
- **T33**: ``compute_kpi_variation`` implementa §7.3 (delta abs/pct, dirección
  derivada del absoluto, ``has_reference=false`` sin baseline, ``baseline=0``
  ⇒ ``delta_pct=null``).

Se puede ejecutar con pytest o directamente::

    py backend/tests/test_dashboard_f4.py
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


def _install_stubs() -> None:
    for name, path in (
        ("app", _BACKEND / "app"),
        ("app.core", _BACKEND / "app" / "core"),
        ("app.models", _BACKEND / "app" / "models"),
        ("app.services", _BACKEND / "app" / "services"),
    ):
        pkg = types.ModuleType(name)
        pkg.__path__ = [str(path)]
        sys.modules.setdefault(name, pkg)

    logging_mod = types.ModuleType("app.core.logging")
    logging_mod.get_logger = logging.getLogger  # type: ignore[attr-defined]
    logging_mod.get_correlation_id = lambda: "tr-test"  # type: ignore[attr-defined]
    sys.modules["app.core.logging"] = logging_mod

    config_mod = types.ModuleType("app.config")

    class _Settings:
        redis_url = ""
        ws_ticket_ttl_seconds = 60
        canonical_timezone = "America/Argentina/Buenos_Aires"

    config_mod.Settings = _Settings  # type: ignore[attr-defined]
    config_mod.get_settings = lambda: _Settings()  # type: ignore[attr-defined]
    sys.modules["app.config"] = config_mod

    tables_mod = types.ModuleType("app.models.tables")
    tables_mod.KPIS = (  # type: ignore[attr-defined]
        "total_consultas_sifcop",
        "personas_capturadas",
        "vehiculos_secuestrados",
        "armas_secuestradas",
    )
    tables_mod.TURNOS = ("MAÑANA", "TARDE", "NOCHE")  # type: ignore[attr-defined]
    tables_mod.agg_hourly = object()  # type: ignore[attr-defined]
    tables_mod.agg_daily = object()  # type: ignore[attr-defined]
    sys.modules["app.models.tables"] = tables_mod

    sqlalchemy_mod = types.ModuleType("sqlalchemy")
    sqlalchemy_mod.select = lambda *a, **k: None  # type: ignore[attr-defined]
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


def _load(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_install_stubs()
ticket = _load("app.services.ticket", _BACKEND / "app" / "services" / "ticket.py")
aggregate = _load("app.services.aggregate", _BACKEND / "app" / "services" / "aggregate.py")


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# =============================================================================
# T29 — ticket WSS de un solo uso (RNF-03.d, §10.3)
# =============================================================================
def test_ticket_encodes_sub_capabilities_room() -> None:
    store = ticket.WsTicketStore(ticket.Settings())
    tkt = _run(
        store.issue(
            sub="operador-1",
            roles=frozenset({"supervisor"}),
            capabilities=frozenset({"dash.view.live", "dash.export.csv"}),
            room_id="sala-central",
        )
    )
    assert tkt.startswith("tkt_")
    payload = _run(store.redeem(tkt))
    assert payload is not None
    assert payload["sub"] == "operador-1"
    assert payload["room_id"] == "sala-central"
    assert set(payload["capabilities"]) == {"dash.view.live", "dash.export.csv"}


def test_ticket_is_single_use() -> None:
    store = ticket.WsTicketStore(ticket.Settings())
    tkt = _run(
        store.issue(
            sub="operador-1",
            roles=frozenset(),
            capabilities=frozenset({"dash.view.live"}),
            room_id="sala-central",
        )
    )
    assert _run(store.redeem(tkt)) is not None
    # Segundo intento: el ticket ya fue consumido → 4401 en la apertura WSS.
    assert _run(store.redeem(tkt)) is None


def test_ticket_rejects_unknown_or_malformed() -> None:
    store = ticket.WsTicketStore(ticket.Settings())
    assert _run(store.redeem("")) is None
    assert _run(store.redeem("no-es-un-ticket")) is None
    assert _run(store.redeem("tkt_" + "x" * 40)) is None


# =============================================================================
# T33 — variación "vs ayer" (§7.3)
# =============================================================================
def test_variation_positive() -> None:
    v = aggregate.compute_kpi_variation(184732, 181612)
    assert v["delta_abs"] == 3120
    assert v["direction"] == "up"
    assert v["has_reference"] is True
    assert v["baseline_value"] == 181612
    assert v["delta_pct"] == round(3120 / 181612 * 100, 2)


def test_variation_negative_and_flat_use_abs_delta() -> None:
    down = aggregate.compute_kpi_variation(37, 43)
    assert (down["delta_abs"], down["direction"]) == (-6, "down")
    flat = aggregate.compute_kpi_variation(10, 10)
    assert (flat["delta_abs"], flat["direction"]) == (0, "flat")


def test_no_reference_has_reference_false() -> None:
    v = aggregate.compute_kpi_variation(10, None)
    assert v["has_reference"] is False
    assert v["delta_abs"] is None
    assert v["delta_pct"] is None
    assert v["direction"] == "flat"


def test_zero_baseline_only_absolute() -> None:
    v = aggregate.compute_kpi_variation(5, 0)
    assert v["has_reference"] is True
    assert v["baseline_value"] == 0
    assert v["delta_abs"] == 5
    assert v["delta_pct"] is None
    assert v["direction"] == "up"


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
