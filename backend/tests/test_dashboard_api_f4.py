"""Tests unitarios mínimos de los endpoints de dashboard/auditoría (F4).

Cubre, con *stubs* mínimos (sin fastapi/sqlalchemy/redis instalados), los
contratos de T30/T31/T32 que no dependen de infraestructura real:

- **T30** ``GET /dashboard/snapshot``: ``503`` sin instantánea, ``200`` con
  sobre ``indicators.snapshot`` y ``409`` cuando Redis espeja un ``seq`` mayor
  (funciona sin Redis / lee PostgreSQL).
- **T31** límite de rango por capacidad (90 d supervisor vs auditor) y cabecera
  de auditoría del CSV de exportación.
- **T32** serialización de eventos de auditoría sin PII y filtros.

Se puede ejecutar con pytest o directamente::

    py backend/tests/test_dashboard_api_f4.py
"""

from __future__ import annotations

import asyncio
import importlib.util
import logging
import sys
import types
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# =============================================================================
# Stubs de dependencias externas ausentes
# =============================================================================
class _StubAPIError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


class _JSONResponse:
    def __init__(self, status_code: int = 200, content: Any = None, headers: Any = None) -> None:
        self.status_code = status_code
        self.content = content
        self.headers = headers


class _Response(_JSONResponse):
    pass


class _Col:
    def __init__(self, name: str) -> None:
        self.name = name

    def __eq__(self, other: Any) -> object:  # type: ignore[override]
        return object()

    def __ge__(self, other: Any) -> object:  # type: ignore[override]
        return object()

    def __le__(self, other: Any) -> object:  # type: ignore[override]
        return object()

    def in_(self, other: Any) -> object:
        return object()

    def is_(self, other: Any) -> object:
        return object()

    def desc(self) -> object:
        return object()


class _Table:
    def __init__(self, name: str, columns: tuple[str, ...]) -> None:
        self.name = name
        self.c = types.SimpleNamespace(**{col: _Col(col) for col in columns})


class _Stmt:
    def where(self, *a: Any) -> "_Stmt":
        return self

    def order_by(self, *a: Any) -> "_Stmt":
        return self

    def offset(self, *a: Any) -> "_Stmt":
        return self

    def limit(self, *a: Any) -> "_Stmt":
        return self


class _Result:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def all(self) -> list[Any]:
        return list(self._rows)

    def first(self) -> Any:
        return self._rows[0] if self._rows else None

    def scalar_one_or_none(self) -> Any:
        return self._rows[0] if self._rows else None


class _Session:
    def __init__(self, result: _Result) -> None:
        self._result = result

    async def execute(self, statement: Any) -> _Result:
        return self._result


class _Bus:
    def __init__(self, last_seq: int | None) -> None:
        self._last_seq = last_seq

    async def get_last_seq(self, room_id: str) -> int | None:
        return self._last_seq


class _Request:
    class _Client:
        host = "203.0.113.9"

    def __init__(self) -> None:
        self.client = _Request._Client()
        self.headers: dict[str, str] = {"User-Agent": "pytest"}


class _Row:
    def __init__(self) -> None:
        self.payload = {
            "schema_version": "1.0.0",
            "event_id": "018f1d2e-3a4b-7c5d-8e6f-0a1b2c3d4e5f",
            "doc_id": "sifcop-resumen",
            "data_date": "2026-10-03",
            "tz": "America/Argentina/Buenos_Aires",
            "payload": {"kpis": {}},
        }
        self.data_date = date(2026, 10, 3)
        self.updated_at = datetime(2026, 10, 3, 14, 22, 5, tzinfo=timezone.utc)
        self.seq = 10427
        self.agent_id = "01924f3a-1c2b-7def-8a01-000000000001"
        self.event_id = "018f1d2e-3a4b-7c5d-8e6f-0a1b2c3d4e5f"


class _APIRouter:
    def __init__(self, *a: Any, **k: Any) -> None:
        pass

    def _decorator(self, *a: Any, **k: Any) -> Any:
        def _wrap(func: Any) -> Any:
            return func

        return _wrap

    get = _decorator
    post = _decorator
    put = _decorator
    delete = _decorator
    websocket = _decorator


def _install_stubs() -> None:
    for name, path in (
        ("app", _BACKEND / "app"),
        ("app.core", _BACKEND / "app" / "core"),
        ("app.models", _BACKEND / "app" / "models"),
        ("app.services", _BACKEND / "app" / "services"),
        ("app.api", _BACKEND / "app" / "api"),
    ):
        pkg = types.ModuleType(name)
        pkg.__path__ = [str(path)]  # type: ignore[attr-defined]
        sys.modules.setdefault(name, pkg)

    fastapi_mod = types.ModuleType("fastapi")
    fastapi_mod.APIRouter = _APIRouter  # type: ignore[attr-defined]
    fastapi_mod.Depends = lambda f=None, **k: f  # type: ignore[attr-defined]
    fastapi_mod.Query = lambda default=None, **k: default  # type: ignore[attr-defined]
    fastapi_mod.Request = _Request  # type: ignore[attr-defined]
    sys.modules["fastapi"] = fastapi_mod

    responses_mod = types.ModuleType("starlette.responses")
    responses_mod.JSONResponse = _JSONResponse  # type: ignore[attr-defined]
    responses_mod.Response = _Response  # type: ignore[attr-defined]
    starlette_mod = types.ModuleType("starlette")
    starlette_mod.responses = responses_mod  # type: ignore[attr-defined]
    sys.modules["starlette"] = starlette_mod
    sys.modules["starlette.responses"] = responses_mod

    sqlalchemy_mod = types.ModuleType("sqlalchemy")
    sqlalchemy_mod.select = lambda *a, **k: _Stmt()  # type: ignore[attr-defined]
    sqlalchemy_mod.or_ = lambda *a: object()  # type: ignore[attr-defined]
    sqlalchemy_mod.func = lambda *a, **k: _Stmt()  # type: ignore[attr-defined]
    ext_mod = types.ModuleType("sqlalchemy.ext")
    asyncio_mod = types.ModuleType("sqlalchemy.ext.asyncio")
    asyncio_mod.AsyncSession = object  # type: ignore[attr-defined]
    sys.modules["sqlalchemy"] = sqlalchemy_mod
    sys.modules["sqlalchemy.ext"] = ext_mod
    sys.modules["sqlalchemy.ext.asyncio"] = asyncio_mod

    errors_mod = types.ModuleType("app.core.errors")

    def _raise(code: str, message: str, *, status_code: int | None = None) -> Any:
        status = (
            status_code
            if status_code is not None
            else {
                "UNAUTHORIZED": 401,
                "FORBIDDEN": 403,
                "CAPACIDAD_DENEGADA": 403,
                "CONFLICT": 409,
                "BAD_REQUEST": 400,
                "UNAVAILABLE": 503,
            }.get(code, 500)
        )
        raise _StubAPIError(status, code, message)

    errors_mod.raise_http_error = _raise  # type: ignore[attr-defined]
    sys.modules["app.core.errors"] = errors_mod

    logging_mod = types.ModuleType("app.core.logging")
    logging_mod.get_logger = logging.getLogger  # type: ignore[attr-defined]
    logging_mod.get_correlation_id = lambda: "tr-test"  # type: ignore[attr-defined]
    sys.modules["app.core.logging"] = logging_mod

    config_mod = types.ModuleType("app.config")

    class _Settings:
        default_room_id = "sala-central"
        canonical_timezone = "America/Argentina/Buenos_Aires"
        history_supervisor_max_days = 90
        history_auditor_max_days = 1826

    config_mod.get_settings = lambda: _Settings()  # type: ignore[attr-defined]
    config_mod.Settings = _Settings  # type: ignore[attr-defined]
    sys.modules["app.config"] = config_mod

    tables_mod = types.ModuleType("app.models.tables")
    tables_mod.KPIS = (
        "total_consultas_sifcop",
        "personas_capturadas",
        "vehiculos_secuestrados",
        "armas_secuestradas",
    )
    tables_mod.REGIONAL_UNITS = ("capital", "sur", "este", "oeste", "norte")
    tables_mod.TURNOS = ("MAÑANA", "TARDE", "NOCHE")
    tables_mod.snapshot_current = _Table(
        "snapshot_current",
        ("doc_id", "event_id", "agent_id", "payload", "data_date", "seq", "updated_at"),
    )
    tables_mod.agg_hourly = _Table(
        "agg_hourly", ("bucket", "kpi_id", "unidad_id", "turno_id", "value", "baseline_value")
    )
    tables_mod.agg_daily = _Table(
        "agg_daily", ("bucket", "kpi_id", "unidad_id", "turno_id", "value", "baseline_value")
    )
    tables_mod.consulta_event = _Table(
        "consulta_event",
        (
            "event_id",
            "doc_id",
            "row_index",
            "seq",
            "received_at",
            "correlation_id",
            "fecha_consulta",
            "hora_consulta",
            "turno",
            "jerarquia",
            "personal_policial",
            "jefatura_regional",
            "dependencias",
            "tipo_consulta",
            "identificacion",
            "tipo_arma_vehiculo",
            "resultado",
            "causas_penales",
            "registro_legajo",
            "autoridad_judicial",
            "sistema_utilizado",
            "tramite_devuelto",
            "hora_resp",
            "personal_que_informa",
            "cargo",
            "operativos_preventivos",
        ),
    )
    tables_mod.audit_event = _Table(
        "audit_event",
        (
            "id",
            "ts",
            "actor",
            "action",
            "resource",
            "result",
            "ip",
            "user_agent",
            "correlation_id",
            "schema_version",
        ),
    )
    sys.modules["app.models.tables"] = tables_mod

    aggregate_mod = types.ModuleType("app.services.aggregate")

    async def _enrich_payload(_session: Any, payload: Any, **_k: Any) -> Any:
        return payload

    aggregate_mod.enrich_payload = _enrich_payload  # type: ignore[attr-defined]
    aggregate_mod.canonical_tz = lambda: timezone.utc  # type: ignore[attr-defined]
    sys.modules["app.services.aggregate"] = aggregate_mod

    audit_svc = types.ModuleType("app.services.audit")

    async def _record_audit(**_k: Any) -> None:
        return None

    audit_svc.record_audit = _record_audit  # type: ignore[attr-defined]
    sys.modules["app.services.audit"] = audit_svc

    bus_mod = types.ModuleType("app.services.bus")
    bus_mod.attach_freshness_quality = lambda payload, **k: payload  # type: ignore[attr-defined]
    bus_mod.build_snapshot_message = lambda **k: {"type": "indicators.snapshot", **k}  # type: ignore[attr-defined]
    _bus_holder: dict[str, Any] = {"bus": _Bus(None)}
    bus_mod.get_bus = lambda: _bus_holder["bus"]  # type: ignore[attr-defined]
    bus_mod._holder = _bus_holder  # type: ignore[attr-defined]
    sys.modules["app.services.bus"] = bus_mod

    capacity_mod = types.ModuleType("app.services.capacity")

    class _Operator:
        def __init__(self, sub: str, caps: set[str]) -> None:
            self.sub = sub
            self.roles = frozenset()
            self.capabilities = frozenset(caps)

        def has_capacity(self, capability: str) -> bool:
            return capability in self.capabilities

    def _require_capacity(capability: str, identity: Any) -> None:
        if not identity.has_capacity(capability):
            _raise("CAPACIDAD_DENEGADA", "denegado")

    capacity_mod.OperatorIdentity = _Operator  # type: ignore[attr-defined]
    capacity_mod.get_operator = lambda: None  # type: ignore[attr-defined]
    capacity_mod.require_capacity = _require_capacity  # type: ignore[attr-defined]
    capacity_mod.CAP_DASH_VIEW_LIVE = "dash.view.live"  # type: ignore[attr-defined]
    capacity_mod.CAP_DASH_VIEW_HISTORY = "dash.view.history"  # type: ignore[attr-defined]
    capacity_mod.CAP_DASH_EXPORT_CSV = "dash.export.csv"  # type: ignore[attr-defined]
    capacity_mod.CAP_AUDIT_VIEW = "audit.view"  # type: ignore[attr-defined]
    sys.modules["app.services.capacity"] = capacity_mod

    db_mod = types.ModuleType("app.services.db")
    db_mod.session_dependency = lambda: None  # type: ignore[attr-defined]
    sys.modules["app.services.db"] = db_mod


def _load(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    getattr(spec.loader, "exec_module")(module)
    return module


_install_stubs()
dashboard = _load("app.api.dashboard", _BACKEND / "app" / "api" / "dashboard.py")
audit = _load("app.api.audit", _BACKEND / "app" / "api" / "audit.py")
capacity = sys.modules["app.services.capacity"]
bus = sys.modules["app.services.bus"]


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# =============================================================================
# T30 — cold start /dashboard/snapshot
# =============================================================================
def test_snapshot_unavailable_without_data() -> None:
    operator = capacity.OperatorIdentity("op", {"dash.view.live"})
    try:
        _run(
            dashboard.get_snapshot(
                request=_Request(),
                operator=operator,
                session=_Session(_Result([])),
                tz="",
                room_id="",
            )
        )
    except _StubAPIError as exc:
        assert exc.status_code == 503
    else:  # pragma: no cover
        raise AssertionError("se esperaba 503 sin snapshot")


def test_snapshot_conflict_when_wss_seq_is_newer() -> None:
    bus._holder["bus"] = _Bus(last_seq=10428)  # > row.seq (10427)
    operator = capacity.OperatorIdentity("op", {"dash.view.live"})
    try:
        _run(
            dashboard.get_snapshot(
                request=_Request(),
                operator=operator,
                session=_Session(_Result([_Row()])),
                tz="",
                room_id="",
            )
        )
    except _StubAPIError as exc:
        assert exc.status_code == 409
    else:  # pragma: no cover
        raise AssertionError("se esperaba 409 con seq de WSS más nuevo")
    finally:
        bus._holder["bus"] = _Bus(None)


def test_snapshot_ok_without_redis() -> None:
    # Sin Redis: last_seq None → no 409 y se devuelve el snapshot de PostgreSQL.
    bus._holder["bus"] = _Bus(None)
    operator = capacity.OperatorIdentity("op", {"dash.view.live"})
    response = _run(
        dashboard.get_snapshot(
            request=_Request(),
            operator=operator,
            session=_Session(_Result([_Row()])),
            tz="",
            room_id="",
        )
    )
    assert response.status_code == 200
    assert response.content["type"] == "indicators.snapshot"
    assert response.content["seq"] == 10427


# =============================================================================
# T31 — histórico y export CSV
# =============================================================================
def test_history_range_supervisor_vs_auditor() -> None:
    supervisor = capacity.OperatorIdentity("sup", {"dash.view.history"})
    auditor = capacity.OperatorIdentity("aud", {"dash.view.history", "audit.view"})
    assert dashboard._history_max_days(supervisor) == 90
    assert dashboard._history_max_days(auditor) == 1826


def test_export_csv_has_audit_header() -> None:
    payload = {
        "kpis": {
            "total_consultas_sifcop": {
                "label": "Total Consultas SIFCOP",
                "value": 184732,
                "delta_abs": 3120,
                "delta_pct": 1.72,
            }
        },
        "regional": [],
        "turnos": [],
        "ranking": {"dependencias": []},
    }
    csv_text = dashboard._build_csv(payload, sub="op-1", event_id="018f", room_id="sala-central")
    first = csv_text.splitlines()[0]
    assert "generado_por=op-1" in first
    assert "event_id_base=018f" in first
    assert "sala=sala-central" in first
    assert "seccion,clave,label,valor" in csv_text


# =============================================================================
# T32 — /audit/events
# =============================================================================
def test_audit_event_serialization_without_pii() -> None:
    ts = datetime(2026, 10, 3, 14, 22, 5, tzinfo=timezone.utc)
    row = (
        ts,
        "op-1",
        "dashboard.snapshot.read",
        "018f",
        "success",
        "ip-abc123",
        "pytest",
        "tr-1",
        "1.0.0",
    )
    event = audit._event_to_dict(row)
    assert event["actor"] == "op-1"
    assert event["action"] == "dashboard.snapshot.read"
    assert event["ip"].startswith("ip-")  # seudonimizada, nunca la IP completa
    assert event["ts"] == ts.isoformat()


def test_audit_list_requires_capacity() -> None:
    denied = capacity.OperatorIdentity("op", set())
    try:
        _run(
            audit.list_events(
                request=_Request(),
                operator=denied,
                session=_Session(_Result([])),
                from_=None,
                to_=None,
                actor=None,
                action=None,
                event_id=None,
                offset=0,
                limit=100,
            )
        )
    except _StubAPIError as exc:
        assert exc.status_code == 403
    else:  # pragma: no cover
        raise AssertionError("se esperaba 403 sin capacidad audit.view")


def test_audit_list_returns_events() -> None:
    ts = datetime(2026, 10, 3, 14, 22, 5, tzinfo=timezone.utc)
    row = (ts, "op-1", "ws.connected", "sala-central", "success", None, None, "tr-1", "1.0.0")
    operator = capacity.OperatorIdentity("aud", {"audit.view"})
    response = _run(
        audit.list_events(
            request=_Request(),
            operator=operator,
            session=_Session(_Result([row])),
            from_=None,
            to_=None,
            actor=None,
            action=None,
            event_id=None,
            offset=0,
            limit=100,
        )
    )
    assert response.status_code == 200
    assert response.content["meta"]["count"] == 1
    assert response.content["events"][0]["action"] == "ws.connected"


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
