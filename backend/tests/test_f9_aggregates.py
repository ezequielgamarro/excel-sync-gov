"""T65 — Agregados y variación "vs ayer" (RF-02.d, §7.3/§7.3.1, T33).

Verifica el cálculo autoritativo del backend:

- ``_tramo_boundary_utc`` trunca la hora del tramo (base ``ayer_mismo_tramo``)
  a la hora en punto de la zona canónica.
- ``enrich_payload`` recalcula ``delta_abs``/``delta_pct``/``direction`` y
  ``baseline_value`` de los 4 KPIs, y ``variacion_abs``/``variacion_pct`` de los
  3 turnos, con ``comparison = "ayer_mismo_tramo"``.
- Sin baseline (día anterior sin registro) → ``has_reference=false`` y deltas
  ``null`` (nunca ``NaN``/``0``).
- ``baseline_value == 0`` → solo variación absoluta (``delta_pct=null``).

Se carga ``aggregate`` con *stubs* mínimos. Directamente::

    py backend/tests/test_f9_aggregates.py
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_TZ_MINUS_3 = timezone(timedelta(hours=-3))


class _Condition:
    pass


class _Column:
    """Columna de tabla mínima: soporta comparaciones e `in_`/`is_`/`desc`."""

    def __init__(self, name: str) -> None:
        self.name = name

    def __eq__(self, other: Any) -> _Condition:  # type: ignore[override]
        return _Condition()

    def __ne__(self, other: Any) -> _Condition:  # type: ignore[override]
        return _Condition()

    def __lt__(self, other: Any) -> _Condition:
        return _Condition()

    def __le__(self, other: Any) -> _Condition:
        return _Condition()

    def __gt__(self, other: Any) -> _Condition:
        return _Condition()

    def __ge__(self, other: Any) -> _Condition:
        return _Condition()

    def in_(self, *_: Any) -> _Condition:
        return _Condition()

    def is_(self, *_: Any) -> _Condition:
        return _Condition()

    def desc(self) -> "_Column":
        return self

    def asc(self) -> "_Column":
        return self


class _Table:
    def __init__(self, name: str, columns: tuple[str, ...]) -> None:
        self.name = name
        self.c = types.SimpleNamespace(**{column: _Column(column) for column in columns})


class _Select:
    def where(self, *_: Any) -> "_Select":
        return self

    def order_by(self, *_: Any) -> "_Select":
        return self

    def limit(self, *_: Any) -> "_Select":
        return self


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

    class _Settings:
        canonical_timezone = "America/Argentina/Buenos_Aires"

    config_mod = types.ModuleType("app.config")
    config_mod.Settings = _Settings  # type: ignore[attr-defined]
    config_mod.get_settings = lambda: _Settings()  # type: ignore[attr-defined]
    sys.modules["app.config"] = config_mod

    logging_mod = types.ModuleType("app.core.logging")
    logging_mod.get_logger = lambda name: __import__("logging").getLogger(name)  # type: ignore[attr-defined]
    sys.modules["app.core.logging"] = logging_mod

    tables_mod = types.ModuleType("app.models.tables")
    tables_mod.KPIS = (  # type: ignore[attr-defined]
        "total_consultas_sifcop",
        "personas_capturadas",
        "vehiculos_secuestrados",
        "armas_secuestradas",
    )
    tables_mod.TURNOS = ("MAÑANA", "TARDE", "NOCHE")  # type: ignore[attr-defined]
    tables_mod.agg_hourly = _Table(  # type: ignore[attr-defined]
        "agg_hourly", ("value", "kpi_id", "unidad_id", "turno_id", "bucket")
    )
    tables_mod.agg_daily = _Table(  # type: ignore[attr-defined]
        "agg_daily", ("value", "bucket", "kpi_id", "unidad_id", "turno_id")
    )
    sys.modules["app.models.tables"] = tables_mod

    sqlalchemy_mod = types.ModuleType("sqlalchemy")
    sqlalchemy_mod.select = lambda *a, **k: _Select()  # type: ignore[attr-defined]
    ext_mod = types.ModuleType("sqlalchemy.ext")
    asyncio_mod = types.ModuleType("sqlalchemy.ext.asyncio")
    asyncio_mod.AsyncSession = object  # type: ignore[attr-defined]
    sys.modules["sqlalchemy"] = sqlalchemy_mod
    sys.modules["sqlalchemy.ext"] = ext_mod
    sys.modules["sqlalchemy.ext.asyncio"] = asyncio_mod


def _load() -> types.ModuleType:
    try:
        from app.services import aggregate  # noqa: F401

        return aggregate
    except ImportError:
        _install_stubs()
        spec = importlib.util.spec_from_file_location(
            "app.services.aggregate", _BACKEND / "app" / "services" / "aggregate.py"
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules["app.services.aggregate"] = module
        spec.loader.exec_module(module)
        return module


aggregate = _load()
aggregate.canonical_tz = lambda: _TZ_MINUS_3  # type: ignore[attr-defined]


class _Result:
    def __init__(self, value: Any) -> None:
        self.value = value

    def scalar_one_or_none(self) -> Any:
        return self.value


class _SequencedSession:
    """Devuelve un baseline por cada ``execute`` (orden de resolución)."""

    def __init__(self, values: list[Any] | None) -> None:
        self._values = list(values) if values is not None else None

    async def execute(self, _statement: Any) -> _Result:
        if self._values is None:
            return _Result(None)
        return _Result(self._values.pop(0) if self._values else None)


def _payload() -> dict[str, Any]:
    return {
        "kpis": {
            key: {"label": key, "value": value}
            for key, value in (
                ("total_consultas_sifcop", 184732),
                ("personas_capturadas", 4128),
                ("vehiculos_secuestrados", 37),
                ("armas_secuestradas", 12),
            )
        },
        "turnos": [
            {"turno_id": "MAÑANA", "intervenciones": 231},
            {"turno_id": "TARDE", "intervenciones": 318},
            {"turno_id": "NOCHE", "intervenciones": 142},
        ],
        "regional": [],
        "ranking": {"top_n": 5, "dependencias": []},
    }


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def test_tramo_boundary_truncates_to_hour() -> None:
    as_of = datetime(2026, 10, 3, 14, 22, 5, tzinfo=timezone.utc)
    boundary = aggregate._tramo_boundary_utc(as_of, _TZ_MINUS_3)
    # 14:22Z → 11:22 local (-03) → truncado a 11:00 local → 14:00Z.
    assert boundary == datetime(2026, 10, 3, 14, 0, tzinfo=timezone.utc)


def test_enrich_payload_recomputes_kpis_and_turnos() -> None:
    aggregate.clear_baseline_cache()
    # Orden: 4 KPIs → 4 baselines; luego 3 turnos → 3 baselines.
    session = _SequencedSession([181612, 3910, 43, 10, 50, 300, 130])
    enriched = _run(
        aggregate.enrich_payload(
            session,
            _payload(),
            data_date=date(2026, 10, 3),
            as_of=datetime(2026, 10, 3, 14, 22, 5, tzinfo=timezone.utc),
        )
    )
    kpi = enriched["kpis"]["total_consultas_sifcop"]
    assert kpi["delta_abs"] == 3120
    assert kpi["delta_pct"] == round(3120 / 181612 * 100, 2)
    assert kpi["direction"] == "up"
    assert kpi["baseline_value"] == 181612
    assert kpi["comparison"] == "ayer_mismo_tramo"
    assert kpi["has_reference"] is True

    turno = enriched["turnos"][0]
    assert turno["variacion_abs"] == 231 - 50
    assert turno["variacion_pct"] == round((231 - 50) / 50 * 100, 2)


def test_enrich_payload_without_baseline_marks_no_reference() -> None:
    aggregate.clear_baseline_cache()
    session = _SequencedSession(None)  # todas las consultas sin fila
    enriched = _run(
        aggregate.enrich_payload(
            session,
            _payload(),
            data_date=date(2026, 10, 3),
            as_of=datetime(2026, 10, 3, 14, 22, 5, tzinfo=timezone.utc),
        )
    )
    kpi = enriched["kpis"]["armas_secuestradas"]
    assert kpi["has_reference"] is False
    assert kpi["delta_abs"] is None
    assert kpi["delta_pct"] is None
    assert kpi["direction"] == "flat"


def test_zero_baseline_only_absolute_variation() -> None:
    variation = aggregate.compute_kpi_variation(5, 0)
    assert variation["has_reference"] is True
    assert variation["baseline_value"] == 0
    assert variation["delta_abs"] == 5
    assert variation["delta_pct"] is None
    assert variation["direction"] == "up"


def test_format_helpers_are_es_cl() -> None:
    assert aggregate.format_int_es_cl(184732) == "184.732"
    assert aggregate.format_decimal_es_cl(1.71) == "1,71"
    assert aggregate.format_pct_es_cl(1.7) == "1,7"
    assert aggregate.format_pct_es_cl(None) == "—"


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
