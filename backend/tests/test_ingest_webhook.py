"""Test unitario del endpoint de ingesta del webhook (T26, spec §10.1).

Ejercita ``ingest_webhook`` con dobles de la capa de autenticación, validación y
persistencia, verificando los contratos de respuesta clave:

- firma inválida → ``401`` (se rechaza antes de deserializar y se audita);
- anti-replay → ``409`` (``ANTI_REPLAY``);
- idempotencia → ``200`` con ``duplicate: true`` (sin redistribuir);
- aceptado → ``202`` y publicación en el bus.

En entornos sin dependencias (fastapi/sqlalchemy/redis) el cargador instala
*stubs* mínimos (mismo enfoque que ``test_auth_webhook.py``). Se puede ejecutar
con pytest o directamente::

    py backend/tests/test_ingest_webhook.py
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import sys
import types
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_EVENT_ID = uuid.UUID("018f1d2e-3a4b-7c5d-8e6f-0a1b2c3d4e5f")
_WEBHOOK_UUID = "01924f3a-1c2b-7def-8a01-000000000001"
_DOC_ID = "sifcop-resumen"
_ROOM_ID = "sala-central"


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


class _APIRouter:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        self.prefix = kwargs.get("prefix", "")

    def post(self, *args: Any, **kwargs: Any) -> Any:
        def _decorator(func: Any) -> Any:
            return func

        return _decorator


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

    errors_mod = types.ModuleType("app.core.errors")
    errors_mod.APIError = _StubAPIError  # type: ignore[attr-defined]

    def _raise(code: str, message: str, *, status_code: int | None = None) -> Any:
        status = (
            status_code
            if status_code is not None
            else {
                "UNAUTHORIZED": 401,
                "FORBIDDEN": 403,
                "KEY_NOT_ACTIVE": 403,
                "ANTI_REPLAY": 409,
                "PAYLOAD_TOO_LARGE": 413,
                "BAD_REQUEST": 400,
                "SNAPSHOT_INVALID": 422,
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

    audit_mod = types.ModuleType("app.services.audit")
    audit_calls: list[dict[str, Any]] = []

    async def _record_audit(**kwargs: Any) -> None:
        audit_calls.append(kwargs)

    audit_mod.record_audit = _record_audit  # type: ignore[attr-defined]
    audit_mod.calls = audit_calls  # type: ignore[attr-defined]
    sys.modules["app.services.audit"] = audit_mod

    auth_mod = types.ModuleType("app.services.auth")

    class _WebhookIdentity:
        pass

    async def _authenticate_webhook(*_a: Any, **_k: Any) -> Any:  # pragma: no cover
        raise AssertionError("no usado: se parchea por prueba")

    auth_mod.WebhookIdentity = _WebhookIdentity  # type: ignore[attr-defined]
    auth_mod.authenticate_webhook = _authenticate_webhook  # type: ignore[attr-defined]
    sys.modules["app.services.auth"] = auth_mod

    bus_mod = types.ModuleType("app.services.bus")
    bus_calls: list[dict[str, Any]] = []

    async def _publish_snapshot(**kwargs: Any) -> None:
        bus_calls.append(kwargs)

    bus_mod.publish_snapshot = _publish_snapshot  # type: ignore[attr-defined]
    bus_mod.calls = bus_calls  # type: ignore[attr-defined]
    sys.modules["app.services.bus"] = bus_mod

    db_mod = types.ModuleType("app.services.db")

    async def _session_dependency() -> Any:  # pragma: no cover - solo DI
        yield None

    db_mod.session_dependency = _session_dependency  # type: ignore[attr-defined]
    sys.modules["app.services.db"] = db_mod

    ingest_mod = types.ModuleType("app.services.ingest")

    class _IngestResult:
        def __init__(self, seq: int, duplicate: bool) -> None:
            self.seq = seq
            self.duplicate = duplicate

    async def _persist_webhook(*_a: Any, **_k: Any) -> Any:  # pragma: no cover
        raise AssertionError("no usado: se parchea por prueba")

    ingest_mod.IngestResult = _IngestResult  # type: ignore[attr-defined]
    ingest_mod.persist_webhook = _persist_webhook  # type: ignore[attr-defined]
    sys.modules["app.services.ingest"] = ingest_mod

    validation_mod = types.ModuleType("app.services.validation")

    def _enforce_size_limit(*_a: Any, **_k: Any) -> None:
        return None

    def _validate_snapshot(*_a: Any, **_k: Any) -> Any:  # pragma: no cover
        raise AssertionError("no usado: se parchea por prueba")

    validation_mod.enforce_size_limit = _enforce_size_limit  # type: ignore[attr-defined]
    validation_mod.validate_snapshot = _validate_snapshot  # type: ignore[attr-defined]
    sys.modules["app.services.validation"] = validation_mod

    fastapi_mod = types.ModuleType("fastapi")
    fastapi_mod.APIRouter = _APIRouter  # type: ignore[attr-defined]
    fastapi_mod.Depends = lambda dependency=None: dependency  # type: ignore[attr-defined]

    class _Request:
        pass

    fastapi_mod.Request = _Request  # type: ignore[attr-defined]
    sys.modules["fastapi"] = fastapi_mod

    starlette_mod = types.ModuleType("starlette")
    responses_mod = types.ModuleType("starlette.responses")
    responses_mod.JSONResponse = _JSONResponse  # type: ignore[attr-defined]
    starlette_mod.responses = responses_mod  # type: ignore[attr-defined]
    sys.modules["starlette"] = starlette_mod
    sys.modules["starlette.responses"] = responses_mod

    sqlalchemy_mod = types.ModuleType("sqlalchemy")
    ext_mod = types.ModuleType("sqlalchemy.ext")
    asyncio_mod = types.ModuleType("sqlalchemy.ext.asyncio")

    class _AsyncSession:
        pass

    asyncio_mod.AsyncSession = _AsyncSession  # type: ignore[attr-defined]
    sys.modules["sqlalchemy"] = sqlalchemy_mod
    sys.modules["sqlalchemy.ext"] = ext_mod
    sys.modules["sqlalchemy.ext.asyncio"] = asyncio_mod


def _load_module(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    getattr(spec.loader, "exec_module")(module)
    return module


def _load_endpoint() -> types.ModuleType:
    try:
        import fastapi  # noqa: F401
        import sqlalchemy  # noqa: F401

        from app.api import ingest

        return ingest
    except ImportError:
        _install_stubs()
        return _load_module("app.api.ingest", _BACKEND / "app" / "api" / "ingest.py")


ingest = _load_endpoint()


# =============================================================================
# Utilidades de prueba
# =============================================================================
class _FakeClient:
    host = "127.0.0.1"


class _FakeRequest:
    def __init__(self, body: bytes) -> None:
        self._body = body
        self.headers = {"X-Webhook-Id": _WEBHOOK_UUID, "User-Agent": "test"}
        self.client = _FakeClient()

    async def body(self) -> bytes:
        return self._body


class _FakeSession:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def execute(self, *_a: Any, **_k: Any) -> Any:
        return None

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


def _identity() -> Any:
    return types.SimpleNamespace(webhook_id=_WEBHOOK_UUID, doc_id=_DOC_ID, room_id=_ROOM_ID)


def _validated() -> Any:
    return types.SimpleNamespace(
        event_id=_EVENT_ID,
        doc_id=_DOC_ID,
        document={"event_id": str(_EVENT_ID)},
        payload={"turnos": [], "ranking": {"dependencias": []}},
        data_date=date(2026, 10, 3),
        content_sha256="a" * 64,
        rejections=(),
    )


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _json_of(response: Any) -> dict[str, Any]:
    """JSON de la respuesta (funciona con ``JSONResponse`` real o stub)."""
    body = getattr(response, "content", None)
    if body is None:
        body = getattr(response, "body", b"")
    if isinstance(body, bytes):
        return json.loads(body)
    return body


def _expect_api_error(coro: Any) -> Any:
    try:
        _run(coro)
    except Exception as exc:  # noqa: BLE001 - se inspecciona el código de rechazo
        return exc
    raise AssertionError("se esperaba un rechazo y no ocurrió")


# =============================================================================
# Casos
# =============================================================================
def test_invalid_signature_rejected_401() -> None:
    async def _reject(*_a: Any, **_k: Any) -> Any:
        raise _StubAPIError(401, "UNAUTHORIZED", "Firma HMAC-SHA256 inválida.")

    ingest.authenticate_webhook = _reject
    exc = _expect_api_error(ingest.ingest_webhook(_FakeRequest(b"{}"), _FakeSession()))
    assert getattr(exc, "status_code", 0) == 401
    assert getattr(exc, "code", "") == "UNAUTHORIZED"


def test_replay_rejected_409() -> None:
    async def _reject(*_a: Any, **_k: Any) -> Any:
        raise _StubAPIError(409, "ANTI_REPLAY", "Nonce ya visto.")

    ingest.authenticate_webhook = _reject
    exc = _expect_api_error(ingest.ingest_webhook(_FakeRequest(b"{}"), _FakeSession()))
    assert getattr(exc, "status_code", 0) == 409
    assert getattr(exc, "code", "") == "ANTI_REPLAY"


def test_duplicate_returns_200_without_republish() -> None:
    async def _auth(*_a: Any, **_k: Any) -> Any:
        return _identity()

    async def _persist(*_a: Any, **_k: Any) -> Any:
        return types.SimpleNamespace(seq=10427, duplicate=True)

    publish_calls: list[Any] = []

    async def _publish(**kwargs: Any) -> None:
        publish_calls.append(kwargs)

    ingest.authenticate_webhook = _auth
    ingest.validate_snapshot = lambda *a, **k: _validated()
    ingest.enforce_size_limit = lambda *a, **k: None
    ingest.persist_webhook = _persist
    ingest.publish_snapshot = _publish

    session = _FakeSession()
    response = _run(ingest.ingest_webhook(_FakeRequest(b"{}"), session))
    assert getattr(response, "status_code", 0) == 200
    assert _json_of(response)["duplicate"] is True
    assert session.rolled_back is True
    assert publish_calls == []


def test_accepted_returns_202_and_publishes() -> None:
    async def _auth(*_a: Any, **_k: Any) -> Any:
        return _identity()

    async def _persist(*_a: Any, **_k: Any) -> Any:
        return types.SimpleNamespace(seq=10428, duplicate=False)

    publish_calls: list[Any] = []

    async def _publish(**kwargs: Any) -> None:
        publish_calls.append(kwargs)

    ingest.authenticate_webhook = _auth
    ingest.validate_snapshot = lambda *a, **k: _validated()
    ingest.enforce_size_limit = lambda *a, **k: None
    ingest.persist_webhook = _persist
    ingest.publish_snapshot = _publish

    session = _FakeSession()
    response = _run(ingest.ingest_webhook(_FakeRequest(b"{}"), session))
    assert getattr(response, "status_code", 0) == 202
    body = _json_of(response)
    assert body["duplicate"] is False
    assert body["seq"] == 10428
    assert session.committed is True
    assert len(publish_calls) == 1
    assert publish_calls[0]["room_id"] == _ROOM_ID


def test_oversized_payload_rejected_413() -> None:
    async def _auth(*_a: Any, **_k: Any) -> Any:
        return _identity()

    def _too_large(*_a: Any, **_k: Any) -> None:
        raise _StubAPIError(413, "PAYLOAD_TOO_LARGE", "Payload supera el límite.")

    ingest.authenticate_webhook = _auth
    ingest.enforce_size_limit = _too_large
    exc = _expect_api_error(ingest.ingest_webhook(_FakeRequest(b"{}"), _FakeSession()))
    assert getattr(exc, "status_code", 0) == 413
    assert getattr(exc, "code", "") == "PAYLOAD_TOO_LARGE"


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
