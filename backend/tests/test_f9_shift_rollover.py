"""T65 — Rollover de turnos operativos (RF-04.b, OD-12, RISK-11).

Verifica ``_derive_estado`` de ``app.services.reconciliation`` (la misma lógica
que gobierna el estado de los 3 turnos) para los 3 turnos fijos:

- ``MAÑANA`` (06:00–14:00) y ``TARDE`` (14:00–22:00): ``pendiente`` antes,
  ``en_curso`` dentro, ``cerrada`` después.
- ``NOCHE`` (22:00–06:00+1) **cruza medianoche**: ``en_curso`` tanto a las
  23:00 como a las 03:00, ``pendiente`` durante el día.

Se carga ``reconciliation`` con *stubs* mínimos (sin httpx/cryptography/
sqlalchemy) para ejecutarse sin dependencias. Directamente::

    py backend/tests/test_f9_shift_rollover.py
"""

from __future__ import annotations

import importlib.util
import sys
import types
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_TZ = "America/Argentina/Buenos_Aires"


def _install_stubs() -> None:
    for name, path in (
        ("app", _BACKEND / "app"),
        ("app.core", _BACKEND / "app" / "core"),
        ("app.models", _BACKEND / "app" / "models"),
        ("app.services", _BACKEND / "app" / "services"),
    ):
        pkg = types.ModuleType(name)
        pkg.__path__ = [str(path)]  # type: ignore[attr-defined]
        sys.modules.setdefault(name, pkg)

    # --- Dependencias de terceros --------------------------------------------
    httpx_mod = types.ModuleType("httpx")
    httpx_mod.AsyncClient = object  # type: ignore[attr-defined]
    sys.modules["httpx"] = httpx_mod

    crypto = types.ModuleType("cryptography")
    hazmat = types.ModuleType("cryptography.hazmat")
    primitives = types.ModuleType("cryptography.hazmat.primitives")
    primitives.hashes = types.SimpleNamespace(SHA256=object)  # type: ignore[attr-defined]
    primitives.serialization = types.SimpleNamespace(load_pem_private_key=lambda *a, **k: None)  # type: ignore[attr-defined]
    asymmetric = types.ModuleType("cryptography.hazmat.primitives.asymmetric")
    asymmetric.padding = types.SimpleNamespace(PKCS1v15=object)  # type: ignore[attr-defined]
    asymmetric.rsa = types.SimpleNamespace(generate_private_key=lambda *a, **k: None)  # type: ignore[attr-defined]
    primitives.asymmetric = asymmetric  # type: ignore[attr-defined]
    hazmat.primitives = primitives  # type: ignore[attr-defined]
    crypto.hazmat = hazmat  # type: ignore[attr-defined]
    sys.modules["cryptography"] = crypto
    sys.modules["cryptography.hazmat"] = hazmat
    sys.modules["cryptography.hazmat.primitives"] = primitives
    sys.modules["cryptography.hazmat.primitives.asymmetric"] = asymmetric

    sqlalchemy_mod = types.ModuleType("sqlalchemy")
    sqlalchemy_mod.select = lambda *a, **k: None  # type: ignore[attr-defined]
    ext_mod = types.ModuleType("sqlalchemy.ext")
    asyncio_mod = types.ModuleType("sqlalchemy.ext.asyncio")
    asyncio_mod.AsyncSession = object  # type: ignore[attr-defined]
    sys.modules["sqlalchemy"] = sqlalchemy_mod
    sys.modules["sqlalchemy.ext"] = ext_mod
    sys.modules["sqlalchemy.ext.asyncio"] = asyncio_mod

    # --- Configuración / errores / logging -----------------------------------
    class _StubSettings:
        canonical_timezone = _TZ
        default_room_id = "sala-central"
        google_sheets_api_base = "https://sheets.googleapis.com/v4"
        google_sheets_range_suffix = ""
        google_service_account_json = ""
        reconciliation_interval_seconds = 60
        source_health_monitor_seconds = 60
        source_degraded_threshold_seconds = 900

    config_mod = types.ModuleType("app.config")
    config_mod.Settings = _StubSettings  # type: ignore[attr-defined]
    config_mod.get_settings = lambda: _StubSettings()  # type: ignore[attr-defined]
    sys.modules["app.config"] = config_mod

    class _APIError(Exception):
        def __init__(self, status_code: int, code: str, message: str) -> None:
            super().__init__(message)
            self.status_code = status_code
            self.code = code

    errors_mod = types.ModuleType("app.core.errors")
    errors_mod.APIError = _APIError  # type: ignore[attr-defined]
    errors_mod.raise_http_error = lambda code, message, **k: (_ for _ in ()).throw(  # type: ignore[attr-defined]
        _APIError(500, code, message)
    )
    sys.modules["app.core.errors"] = errors_mod

    logging_mod = types.ModuleType("app.core.logging")
    logging_mod.get_logger = lambda name: __import__("logging").getLogger(name)  # type: ignore[attr-defined]
    sys.modules["app.core.logging"] = logging_mod

    # --- Proyecciones de tablas ----------------------------------------------
    tables_mod = types.ModuleType("app.models.tables")
    tables_mod.KPIS = ("total_consultas_sifcop", "personas_capturadas", "vehiculos_secuestrados", "armas_secuestradas")  # type: ignore[attr-defined]
    tables_mod.REGIONAL_UNITS = ("capital", "sur", "este", "oeste", "norte")  # type: ignore[attr-defined]
    tables_mod.TURNOS = ("MAÑANA", "TARDE", "NOCHE")  # type: ignore[attr-defined]
    tables_mod.snapshot_current = object()  # type: ignore[attr-defined]
    tables_mod.webhook_registry = object()  # type: ignore[attr-defined]
    sys.modules["app.models.tables"] = tables_mod

    # --- Servicios hermanos ---------------------------------------------------
    def _service(name: str, **attrs: Any) -> types.ModuleType:
        mod = types.ModuleType(name)
        for key, value in attrs.items():
            setattr(mod, key, value)
        sys.modules[name] = mod
        return mod

    async def _noop(*_a: Any, **_k: Any) -> None:
        return None

    class _WebhookIdentity:
        pass

    _service("app.services.audit", record_audit=_noop)
    _service("app.services.auth", WebhookIdentity=_WebhookIdentity)
    _service("app.services.bus", publish_snapshot=_noop)
    _service("app.services.db", get_session_factory=lambda: None)
    _service("app.services.ingest", persist_webhook=_noop)
    _service("app.services.source_health", evaluate_source_health=lambda *a, **k: None)
    _service("app.services.validation", validate_snapshot=lambda *a, **k: None)


def _load() -> types.ModuleType:
    try:
        from app.services import reconciliation  # noqa: F401

        return reconciliation
    except ImportError:
        _install_stubs()
        spec = importlib.util.spec_from_file_location(
            "app.services.reconciliation",
            _BACKEND / "app" / "services" / "reconciliation.py",
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules["app.services.reconciliation"] = module
        getattr(spec.loader, "exec_module")(module)
        return module


reconciliation = _load()

_TURNOS = {
    "MAÑANA": {"inicio_min": 360, "fin_min": 840, "label": "MAÑANA (06-14)"},
    "TARDE": {"inicio_min": 840, "fin_min": 1320, "label": "TARDE (14-22)"},
    "NOCHE": {"inicio_min": 1320, "fin_min": 360, "label": "NOCHE (22-06)"},
}


def _estado_at(turno: str, hour: int, minute: int = 0) -> str:
    fixed = datetime(2026, 10, 3, hour, minute, tzinfo=timezone.utc)
    original = reconciliation._local_now
    reconciliation._local_now = lambda tz: fixed
    try:
        return reconciliation._derive_estado(_TURNOS[turno], _TZ)
    finally:
        reconciliation._local_now = original


def test_manana_window() -> None:
    assert _estado_at("MAÑANA", 5) == "pendiente"
    assert _estado_at("MAÑANA", 6) == "en_curso"
    assert _estado_at("MAÑANA", 13, 59) == "en_curso"
    assert _estado_at("MAÑANA", 14) == "cerrada"


def test_tarde_window() -> None:
    assert _estado_at("TARDE", 13, 59) == "pendiente"
    assert _estado_at("TARDE", 14) == "en_curso"
    assert _estado_at("TARDE", 21, 59) == "en_curso"
    assert _estado_at("TARDE", 22) == "cerrada"


def test_noche_crosses_midnight() -> None:
    # 22:00–06:00+1: en curso a ambos lados de medianoche.
    assert _estado_at("NOCHE", 22) == "en_curso"
    assert _estado_at("NOCHE", 23, 59) == "en_curso"
    assert _estado_at("NOCHE", 0) == "en_curso"
    assert _estado_at("NOCHE", 5, 59) == "en_curso"
    # Durante el día el turno NOCHE aún no ha comenzado.
    assert _estado_at("NOCHE", 6) == "pendiente"
    assert _estado_at("NOCHE", 15) == "pendiente"


def test_no_zero_for_pending_state() -> None:
    # RISK-11 / RF-04.b: un turno futuro es `pendiente` (no un 0 de datos).
    assert _estado_at("NOCHE", 12) == "pendiente"
    assert _estado_at("NOCHE", 12) != "cerrada"


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
