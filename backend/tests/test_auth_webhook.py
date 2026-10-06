"""Test unitario de la autenticación del webhook (T23, spec §2.2.1, §9).

Ejercita ``authenticate_webhook`` de extremo a extremo con dobles de la sesión
SQLAlchemy y del secret manager, verificando el **orden fail-closed**:

1. formato de cabeceras → ``401``;
2. ``webhook_id`` desconocido → ``401`` / revocado o inactivo → ``403``;
3. ``key_id`` no vigente → ``403``;
4. firma HMAC-SHA256 inválida → ``401``;
5. timestamp fuera de ±300 s o nonce repetido → ``409`` (``ANTI_REPLAY``).

En entornos sin dependencias (fastapi/sqlalchemy/pydantic) el cargador instala
*stubs* mínimos (mismo enfoque que ``test_webhook_signature.py``). Se puede
ejecutar con pytest o directamente::

    py backend/tests/test_auth_webhook.py
"""

from __future__ import annotations

import hashlib
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

_WEBHOOK_UUID = uuid.UUID("01924f3a-1c2b-7def-8a01-000000000001")
_WEBHOOK_ID = str(_WEBHOOK_UUID)
_KEY_ID = "wk-2026-10"
_NONCE = "7f3c9a2b1d8e4c6f5a0b3d9e8c7f6a1b"
_TS = "2026-10-03T14:22:05Z"
_NOW = datetime(2026, 10, 3, 14, 22, 5, tzinfo=timezone.utc)
_VERSION = "1.0.0"
_DOC_ID = "sheet-central"
_ROOM_ID = "sala-central"
_SECRET = bytes(range(32))


# =============================================================================
# Stubs de dependencias externas ausentes
# =============================================================================
class _Cond:
    def __init__(self, column: _Col, value: Any) -> None:
        self.column = column
        self.value = value


class _Col:
    def __init__(self, table: _Table, name: str) -> None:
        self.table = table
        self.name = name

    def __eq__(self, other: Any) -> _Cond:  # type: ignore[override]
        return _Cond(self, other)


class _Table:
    def __init__(self, name: str, columns: tuple[str, ...]) -> None:
        self.name = name
        self.c = types.SimpleNamespace(**{col: _Col(self, col) for col in columns})


class _Select:
    def __init__(self, columns: tuple[Any, ...]) -> None:
        self.table = columns[0].table
        self.columns = columns

    def where(self, *_conds: Any) -> _Select:
        return self


class _FakeResult:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    async def fetchone(self) -> Any:
        return self._rows[0] if self._rows else None

    async def fetchall(self) -> list[Any]:
        return list(self._rows)


class _FakeSession:
    def __init__(self, *, registry: list[Any] | None = None, secrets: list[Any] | None = None) -> None:
        self._registry = registry or []
        self._secrets = secrets or []

    async def stream(self, statement: _Select) -> _FakeResult:
        rows = self._registry if statement.table.name == "webhook_registry" else self._secrets
        return _FakeResult(rows)


class _FakeSecretManager:
    def __init__(self, secrets: dict[tuple[str, str], bytes]) -> None:
        self._secrets = secrets

    def get_webhook_secret(self, *, webhook_id: str, key_id: str) -> bytes | None:
        return self._secrets.get((webhook_id, key_id))


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

    class _StubSettings:
        replay_clock_skew_seconds = 300
        replay_window_seconds = 600
        redis_url = ""
        webhook_id = ""
        webhook_key_id = ""
        webhook_secret = ""

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
        "UNAUTHORIZED": 401,
        "FORBIDDEN": 403,
        "KEY_NOT_ACTIVE": 403,
        "UNAVAILABLE": 503,
        "ANTI_REPLAY": 409,
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

    # redis.asyncio mínimo (el guard anti-replay se inyecta con backend en
    # memoria: ``redis_url`` vacío, por lo que no se abre cliente real).
    redis_mod = types.ModuleType("redis")
    redis_asyncio_mod = types.ModuleType("redis.asyncio")
    redis_asyncio_mod.from_url = lambda *_a, **_k: None  # type: ignore[attr-defined]
    redis_mod.asyncio = redis_asyncio_mod  # type: ignore[attr-defined]
    sys.modules["redis"] = redis_mod
    sys.modules["redis.asyncio"] = redis_asyncio_mod

    # Auditoría: se registran los rechazos sin base de datos.
    audit_calls: list[dict[str, Any]] = []
    audit_mod = types.ModuleType("app.services.audit")

    async def _record_audit(**kwargs: Any) -> None:
        audit_calls.append(kwargs)

    audit_mod.record_audit = _record_audit  # type: ignore[attr-defined]
    audit_mod.calls = audit_calls  # type: ignore[attr-defined]
    sys.modules["app.services.audit"] = audit_mod

    # SQLAlchemy mínimo.
    sqlalchemy_mod = types.ModuleType("sqlalchemy")
    sqlalchemy_mod.select = lambda *columns: _Select(columns)  # type: ignore[attr-defined]
    sys.modules["sqlalchemy"] = sqlalchemy_mod
    ext_mod = types.ModuleType("sqlalchemy.ext")
    asyncio_mod = types.ModuleType("sqlalchemy.ext.asyncio")

    class _AsyncSession:  # solo para anotaciones/DI en el stub
        pass

    asyncio_mod.AsyncSession = _AsyncSession  # type: ignore[attr-defined]
    sys.modules["sqlalchemy.ext"] = ext_mod
    sys.modules["sqlalchemy.ext.asyncio"] = asyncio_mod

    # FastAPI mínimo.
    fastapi_mod = types.ModuleType("fastapi")
    fastapi_mod.Depends = lambda dependency=None: dependency  # type: ignore[attr-defined]

    class _Request:
        pass

    fastapi_mod.Request = _Request  # type: ignore[attr-defined]
    sys.modules["fastapi"] = fastapi_mod

    # Proyecciones de tablas mínimas (solo las columnas usadas por auth.py).
    tables_mod = types.ModuleType("app.models.tables")
    tables_mod.webhook_registry = _Table(  # type: ignore[attr-defined]
        "webhook_registry", ("webhook_id", "doc_id", "room_id", "estado", "revoked_at")
    )
    tables_mod.webhook_secret = _Table(  # type: ignore[attr-defined]
        "webhook_secret", ("key_id", "webhook_id", "estado", "not_before", "not_after")
    )
    sys.modules["app.models.tables"] = tables_mod

    db_mod = types.ModuleType("app.services.db")

    async def _session_dependency() -> Any:  # pragma: no cover - solo DI
        yield _FakeSession()

    db_mod.session_dependency = _session_dependency  # type: ignore[attr-defined]
    sys.modules["app.services.db"] = db_mod


def _load_module(name: str, filename: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, _BACKEND / "app" / "services" / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    getattr(spec.loader, "exec_module")(module)
    return module


def _load_modules() -> tuple[types.ModuleType, types.ModuleType]:
    try:
        import fastapi  # noqa: F401
        import sqlalchemy  # noqa: F401

        from app.services import auth, webhook_signature

        return auth, webhook_signature
    except ImportError:
        _install_stubs()
        ws = _load_module("app.services.webhook_signature", "webhook_signature.py")
        auth = _load_module("app.services.auth", "auth.py")
        return auth, ws


auth, ws = _load_modules()
replay = sys.modules["app.services.replay"]


# =============================================================================
# Utilidades de prueba
# =============================================================================
def _headers(
    body: bytes,
    secret: bytes = _SECRET,
    *,
    key_id: str = _KEY_ID,
    timestamp: str = _TS,
    webhook_id: str = _WEBHOOK_ID,
    nonce: str = _NONCE,
    **overrides: str,
) -> dict[str, str]:
    content = hashlib.sha256(body).hexdigest()
    canonical = ws.build_canonical_string(
        webhook_id=webhook_id,
        key_id=key_id,
        nonce=nonce,
        timestamp=timestamp,
        schema_version=_VERSION,
        content_sha256=content,
    )
    signature = ws.compute_signature_hex(secret, canonical)
    headers = {
        ws.WEBHOOK_ID_HEADER: webhook_id,
        ws.KEY_ID_HEADER: key_id,
        ws.NONCE_HEADER: nonce,
        ws.TIMESTAMP_HEADER: timestamp,
        ws.VERSION_HEADER: _VERSION,
        ws.SIGNATURE_HEADER: f"sha256={signature}",
    }
    headers.update(overrides)
    return headers


def _registry_row(*, estado: str = "activo", revoked_at: Any = None) -> Any:
    return types.SimpleNamespace(
        estado=estado, revoked_at=revoked_at, doc_id=_DOC_ID, room_id=_ROOM_ID
    )


def _secret_row(
    *,
    key_id: str = _KEY_ID,
    estado: str = "vigente",
    not_before: Any = None,
    not_after: Any = None,
) -> Any:
    return types.SimpleNamespace(
        key_id=key_id,
        webhook_id=_WEBHOOK_UUID,
        estado=estado,
        not_before=not_before,
        not_after=not_after,
    )


def _request(headers: dict[str, str]) -> Any:
    return types.SimpleNamespace(headers=headers)


def _authenticate(
    body: bytes,
    headers: dict[str, str],
    *,
    registry: list[Any] | None = None,
    secrets: list[Any] | None = None,
    secret_material: dict[tuple[str, str], bytes] | None = None,
    now: datetime | None = _NOW,
    guard: Any | None = None,
) -> Any:
    session = _FakeSession(
        registry=[_registry_row()] if registry is None else registry,
        secrets=[_secret_row()] if secrets is None else secrets,
    )
    manager = _FakeSecretManager(
        {(_WEBHOOK_ID, _KEY_ID): _SECRET} if secret_material is None else secret_material
    )
    active_guard = guard if guard is not None else replay.ReplayGuard(replay.get_settings())
    import asyncio

    return asyncio.run(
        auth.authenticate_webhook(
            _request(headers),
            session,
            body=body,
            secret_manager=manager,
            now=now,
            replay_guard=active_guard,
        )
    )


def _expect_reject(callable_: Any) -> Any:
    try:
        callable_()
    except Exception as exc:  # noqa: BLE001 - se inspecciona el código de rechazo
        return exc
    raise AssertionError("se esperaba un rechazo (fail-closed) y no ocurrió")


# =============================================================================
# Casos
# =============================================================================
def test_valid_webhook_returns_identity_and_key_id() -> None:
    body = b'{"event_id":"e1"}'
    identity = _authenticate(body, _headers(body))
    assert identity.webhook_id == _WEBHOOK_ID
    assert identity.key_id == _KEY_ID
    assert identity.doc_id == _DOC_ID
    assert identity.room_id == _ROOM_ID
    assert identity.nonce == _NONCE
    assert identity.content_sha256 == hashlib.sha256(body).hexdigest()


def test_missing_header_rejected_unauthorized() -> None:
    body = b"{}"
    headers = _headers(body)
    del headers[ws.NONCE_HEADER]
    exc = _expect_reject(lambda: _authenticate(body, headers))
    assert getattr(exc, "code", "") == "UNAUTHORIZED"
    assert getattr(exc, "status_code", 0) == 401


def test_unknown_webhook_rejected_unauthorized() -> None:
    body = b"{}"
    exc = _expect_reject(lambda: _authenticate(body, _headers(body), registry=[]))
    assert getattr(exc, "code", "") == "UNAUTHORIZED"


def test_revoked_webhook_rejected_forbidden() -> None:
    body = b"{}"
    exc = _expect_reject(
        lambda: _authenticate(
            body,
            _headers(body),
            registry=[_registry_row(estado="revocado", revoked_at=_NOW)],
        )
    )
    assert getattr(exc, "code", "") == "FORBIDDEN"
    assert getattr(exc, "status_code", 0) == 403


def test_key_id_not_active_rejected_forbidden() -> None:
    body = b"{}"
    exc = _expect_reject(
        lambda: _authenticate(body, _headers(body), secrets=[_secret_row(estado="retirado")])
    )
    assert getattr(exc, "code", "") == "KEY_NOT_ACTIVE"
    assert getattr(exc, "status_code", 0) == 403


def test_invalid_signature_rejected_unauthorized() -> None:
    body = b'{"event_id":"e1"}'
    headers = _headers(b'{"event_id":"e2"}')  # firma de otro cuerpo
    exc = _expect_reject(lambda: _authenticate(body, headers))
    assert getattr(exc, "code", "") == "UNAUTHORIZED"


def test_timestamp_outside_window_rejected_anti_replay() -> None:
    body = b"{}"
    stale = "2026-10-03T13:00:00Z"  # ~82 min atrás (> ±300 s)
    exc = _expect_reject(
        lambda: _authenticate(body, _headers(body, timestamp=stale), now=_NOW)
    )
    assert getattr(exc, "code", "") == "ANTI_REPLAY"
    assert getattr(exc, "status_code", 0) == 409


def test_replayed_nonce_rejected_anti_replay() -> None:
    body = b'{"event_id":"e1"}'
    headers = _headers(body)
    guard = replay.ReplayGuard(replay.get_settings())
    first = _authenticate(body, headers, guard=guard)
    assert first.nonce == _NONCE
    exc = _expect_reject(lambda: _authenticate(body, headers, guard=guard))
    assert getattr(exc, "code", "") == "ANTI_REPLAY"
    assert getattr(exc, "status_code", 0) == 409


def test_rotation_overlap_old_key_accepted() -> None:
    now = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
    old_secret = b"a" * 32
    body = b'{"event_id":"e1"}'
    identity = _authenticate(
        body,
        _headers(body, old_secret, key_id="wk-old", timestamp="2026-10-03T12:00:00Z"),
        secrets=[
            _secret_row(
                key_id="wk-old",
                estado="vigente",
                not_after=now + timedelta(hours=12),
            )
        ],
        secret_material={(_WEBHOOK_ID, "wk-old"): old_secret},
        now=now,
    )
    # La versión saliente sigue vigente dentro del solape de rotación.
    assert identity.key_id == "wk-old"


def test_rotation_overlap_expired_old_key_rejected_forbidden() -> None:
    now = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
    old_secret = b"a" * 32
    body = b'{"event_id":"e1"}'
    exc = _expect_reject(
        lambda: _authenticate(
            body,
            _headers(body, old_secret, key_id="wk-old", timestamp="2026-10-03T12:00:00Z"),
            secrets=[
                _secret_row(
                    key_id="wk-old",
                    estado="vigente",
                    not_after=now - timedelta(hours=1),  # solape cerrado
                )
            ],
            secret_material={(_WEBHOOK_ID, "wk-old"): old_secret},
            now=now,
        )
    )
    assert getattr(exc, "code", "") == "KEY_NOT_ACTIVE"


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
