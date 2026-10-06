"""Test unitario de la provisión/rotación del secreto del webhook (T27, §9.3/§10.1).

Cubre el comportamiento exigido por T27:

- El secreto se entrega **una sola vez** y el material va al secret manager; la
  metadata persistida **no** contiene el material (RNF-02.e/§9.5).
- La rotación mantiene un **solape de 24 h** entre la versión nueva y la
  retirada (``not_after`` de la saliente y ``overlap_until`` de la respuesta).
- Se emite **auditoría** ``platform.webhook.secret_rotated`` (actor/``sub`` y
  ``correlation_id``).

En entornos sin dependencias (fastapi/sqlalchemy/pydantic) el cargador instala
*stubs* mínimos (mismo enfoque que ``test_auth_webhook.py``). Se puede ejecutar
con pytest o directamente::

    py backend/tests/test_webhook_rotation.py
"""

from __future__ import annotations

import importlib.util
import logging
import sys
import types
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_WEBHOOK_UUID = uuid.UUID("01924f3a-1c2b-7def-8a01-000000000002")
_NOW = datetime(2026, 10, 4, 12, 0, tzinfo=timezone.utc)
_ACTOR = "admin-1"
_CORRELATION = "tr-test27"


class _FakeSecretStore:
    """Secret manager mínimo en memoria (nunca la BD)."""

    def __init__(self) -> None:
        self.secrets: dict[tuple[str, str], bytes] = {}

    def put_webhook_secret(self, *, webhook_id: str, key_id: str, material: bytes) -> None:
        self.secrets[(webhook_id, key_id)] = material


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

    class _StubSettings:
        default_room_id = "sala-central"

    config_mod = types.ModuleType("app.config")
    config_mod.Settings = _StubSettings  # type: ignore[attr-defined]
    config_mod.get_settings = lambda: _StubSettings()  # type: ignore[attr-defined]
    sys.modules["app.config"] = config_mod

    class _StubAPIError(Exception):
        def __init__(self, status_code: int, code: str, message: str) -> None:
            super().__init__(message)
            self.status_code = status_code
            self.code = code
            self.message = message

    _status = {
        "BAD_REQUEST": 400,
        "FORBIDDEN": 403,
        "NOT_FOUND": 404,
        "CONFLICT": 409,
        "UNPROCESSABLE": 422,
    }

    def _raise(code: str, message: str, *, status_code: int | None = None) -> Any:
        raise _StubAPIError(status_code or _status.get(code, 500), code, message)

    errors_mod = types.ModuleType("app.core.errors")
    errors_mod.APIError = _StubAPIError  # type: ignore[attr-defined]
    errors_mod.raise_http_error = _raise  # type: ignore[attr-defined]
    sys.modules["app.core.errors"] = errors_mod

    logging_mod = types.ModuleType("app.core.logging")
    logging_mod.get_logger = logging.getLogger  # type: ignore[attr-defined]
    sys.modules["app.core.logging"] = logging_mod

    # Auditoría: se recoge la llamada sin base de datos.
    audit_calls: list[dict[str, Any]] = []
    audit_mod = types.ModuleType("app.services.audit")

    async def _record_audit(**kwargs: Any) -> None:
        audit_calls.append(kwargs)

    audit_mod.record_audit = _record_audit  # type: ignore[attr-defined]
    audit_mod.calls = audit_calls  # type: ignore[attr-defined]
    sys.modules["app.services.audit"] = audit_mod

    # SQLAlchemy mínimo (los helpers de persistencia se sustituyen en el test).
    sqlalchemy_mod = types.ModuleType("sqlalchemy")
    sqlalchemy_mod.select = lambda *a, **k: None  # type: ignore[attr-defined]
    sqlalchemy_mod.insert = lambda *a, **k: None  # type: ignore[attr-defined]
    sqlalchemy_mod.update = lambda *a, **k: None  # type: ignore[attr-defined]
    sqlalchemy_mod.or_ = lambda *a, **k: None  # type: ignore[attr-defined]
    sqlalchemy_mod.func = types.SimpleNamespace(  # type: ignore[attr-defined]
        least=lambda *a, **k: None, coalesce=lambda *a, **k: None
    )
    sys.modules["sqlalchemy"] = sqlalchemy_mod
    ext_mod = types.ModuleType("sqlalchemy.ext")
    asyncio_mod = types.ModuleType("sqlalchemy.ext.asyncio")

    class _AsyncSession:
        pass

    asyncio_mod.AsyncSession = _AsyncSession  # type: ignore[attr-defined]
    sys.modules["sqlalchemy.ext"] = ext_mod
    sys.modules["sqlalchemy.ext.asyncio"] = asyncio_mod

    tables_mod = types.ModuleType("app.models.tables")
    tables_mod.webhook_registry = object()  # type: ignore[attr-defined]
    tables_mod.webhook_secret = object()  # type: ignore[attr-defined]
    sys.modules["app.models.tables"] = tables_mod


def _load_module() -> types.ModuleType:
    _install_stubs()
    spec = importlib.util.spec_from_file_location(
        "app.services.agents", _BACKEND / "app" / "services" / "agents.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["app.services.agents"] = module
    spec.loader.exec_module(module)
    return module


agents = _load_module()
audit_mod = sys.modules["app.services.audit"]

# Estado simulado de la BD, reiniciado por prueba.
_state: dict[str, Any] = {}


def _install_persistence_doubles() -> None:
    async def _fetch_registry(session: Any, webhook_uuid: uuid.UUID) -> Any:
        return _state.get("registry_row")

    async def _fetch_active_key_ids(
        session: Any, webhook_uuid: uuid.UUID, momento: datetime
    ) -> list[str]:
        return list(_state.get("active_keys", []))

    async def _key_id_exists(session: Any, key_id: str) -> bool:
        return key_id in _state.get("existing_key_ids", set())

    async def _find_active_by_doc(session: Any, doc_id: str) -> Any:
        return _state.get("active_doc_webhook")

    async def _insert_registry(session: Any, **kwargs: Any) -> None:
        _state.setdefault("inserted_registry", []).append(kwargs)

    async def _insert_secret(session: Any, **kwargs: Any) -> None:
        _state.setdefault("inserted_secrets", []).append(kwargs)

    async def _retire_previous_keys(session: Any, **kwargs: Any) -> None:
        _state["retired"] = kwargs

    agents._fetch_registry = _fetch_registry  # type: ignore[attr-defined]
    agents._fetch_active_key_ids = _fetch_active_key_ids  # type: ignore[attr-defined]
    agents._key_id_exists = _key_id_exists  # type: ignore[attr-defined]
    agents._find_active_by_doc = _find_active_by_doc  # type: ignore[attr-defined]
    agents._insert_registry = _insert_registry  # type: ignore[attr-defined]
    agents._insert_secret = _insert_secret  # type: ignore[attr-defined]
    agents._retire_previous_keys = _retire_previous_keys  # type: ignore[attr-defined]


_install_persistence_doubles()


def _reset() -> None:
    _state.clear()
    audit_mod.calls.clear()


def _run(coro: Any) -> Any:
    import asyncio

    return asyncio.run(coro)


# =============================================================================
# Casos
# =============================================================================
def test_new_provisioning_returns_secret_once_without_overlap() -> None:
    _reset()
    store = _FakeSecretStore()
    result = _run(
        agents.rotate_webhook_secret(
            object(),
            actor=_ACTOR,
            correlation_id=_CORRELATION,
            doc_id="sheet-central",
            secret_store=store,
            now=_NOW,
        )
    )
    # Alta nueva: UUIDv7 generado, sin solape.
    assert result.created is True
    assert uuid.UUID(result.webhook_id).version == 7
    assert result.overlap_until is None
    # Secreto de 256 bits en hex; entregado una sola vez y custodiado en el store.
    assert len(result.secret) == 64
    assert bytes.fromhex(result.secret) in store.secrets.values()
    # El registro se crea y la metadata no contiene material.
    assert _state["inserted_registry"][0]["doc_id"] == "sheet-central"
    assert _state["inserted_registry"][0]["room_id"] == "sala-central"
    secret_row = _state["inserted_secrets"][0]
    assert secret_row["key_id"] == result.key_id
    assert secret_row["webhook_uuid"] == uuid.UUID(result.webhook_id)
    assert "secret" not in secret_row
    assert result.secret not in str(secret_row)


def test_rotation_keeps_24h_overlap_and_audits() -> None:
    _reset()
    store = _FakeSecretStore()
    # El secret manager ya custodia la versión saliente antes de rotar.
    store.secrets[(str(_WEBHOOK_UUID), "wk-old")] = b"a" * 32
    _state["registry_row"] = types.SimpleNamespace(
        estado="activo", revoked_at=None, doc_id="sheet-central", room_id="sala-central"
    )
    _state["active_keys"] = ["wk-old"]

    result = _run(
        agents.rotate_webhook_secret(
            object(),
            actor=_ACTOR,
            correlation_id=_CORRELATION,
            webhook_id=str(_WEBHOOK_UUID),
            secret_store=store,
            now=_NOW,
        )
    )

    # Rotación: el origen ya existía y la versión saliente queda solapada 24 h.
    assert result.created is False
    assert result.webhook_id == str(_WEBHOOK_UUID)
    assert result.overlap_until == _NOW + timedelta(hours=24)
    assert _state["retired"]["overlap_until"] == _NOW + timedelta(hours=24)
    assert _state["retired"]["new_key_id"] == result.key_id
    # Ambas versiones coexisten en el secret manager (solape).
    assert (str(_WEBHOOK_UUID), "wk-old") in store.secrets
    assert (str(_WEBHOOK_UUID), result.key_id) in store.secrets
    assert len(store.secrets) == 2

    # Auditoría de la rotación: acción, actor (sub) y correlation_id.
    assert audit_mod.calls, "se esperaba auditoría de rotación"
    audit = audit_mod.calls[-1]
    assert audit["action"] == "platform.webhook.secret_rotated"
    assert audit["actor"] == _ACTOR
    assert audit["correlation_id"] == _CORRELATION
    assert audit["result"] == "success"
    assert result.secret not in str(audit)


def test_provided_key_id_conflict_rejected() -> None:
    _reset()
    _state["existing_key_ids"] = {"wk-2026-10"}
    exc = None
    try:
        _run(
            agents.rotate_webhook_secret(
                object(),
                actor=_ACTOR,
                doc_id="sheet-central",
                key_id="wk-2026-10",
                secret_store=_FakeSecretStore(),
                now=_NOW,
            )
        )
    except Exception as error:  # noqa: BLE001 - se inspecciona el código
        exc = error
    assert exc is not None and getattr(exc, "code", "") == "CONFLICT"


def test_rotation_of_unknown_webhook_rejected() -> None:
    _reset()
    _state["registry_row"] = None
    exc = None
    try:
        _run(
            agents.rotate_webhook_secret(
                object(),
                actor=_ACTOR,
                webhook_id=str(_WEBHOOK_UUID),
                secret_store=_FakeSecretStore(),
                now=_NOW,
            )
        )
    except Exception as error:  # noqa: BLE001 - se inspecciona el código
        exc = error
    assert exc is not None and getattr(exc, "code", "") == "NOT_FOUND"


def test_new_provisioning_duplicate_doc_rejected() -> None:
    _reset()
    _state["active_doc_webhook"] = _WEBHOOK_UUID
    exc = None
    try:
        _run(
            agents.rotate_webhook_secret(
                object(),
                actor=_ACTOR,
                doc_id="sheet-central",
                secret_store=_FakeSecretStore(),
                now=_NOW,
            )
        )
    except Exception as error:  # noqa: BLE001 - se inspecciona el código
        exc = error
    assert exc is not None and getattr(exc, "code", "") == "CONFLICT"


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
