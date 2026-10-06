"""Tests del middleware RBAC por capacidad, deny por defecto (T37, RNF-03.c/h).

Se cargan ``app.core.rbac`` con *stubs* mínimos (sin fastapi/sqlalchemy/
prometheus) para probar la política de rutas y el rechazo/permiso del
middleware.

    py backend/tests/test_rbac_f5.py
"""

from __future__ import annotations

import asyncio
import importlib.util
import sys
import types
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


# =============================================================================
# Stubs
# =============================================================================
class _APIError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


class _Headers:
    def __init__(self, scope: Any = None, **_: Any) -> None:
        self._data: dict[str, str] = {}
        if isinstance(scope, dict):
            for key, value in scope.get("headers", []):
                self._data[key.decode("latin-1").lower()] = value.decode("latin-1")

    def get(self, key: str, default: str = "") -> str:
        return self._data.get(key.lower(), default)


class _JSONResponse:
    def __init__(self, status_code: int = 200, content: Any = None, headers: Any = None) -> None:
        self.status_code = status_code
        self.content = content
        self.headers = headers
        self.sent = False

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        self.sent = True
        await send({"type": "http.response.start", "status": self.status_code})


class _Counter:
    def labels(self, **_: Any) -> "_Counter":
        return self

    def inc(self) -> None:
        pass


class _Operator:
    def __init__(self, sub: str, caps: set[str]) -> None:
        self.sub = sub
        self.capabilities = frozenset(caps)
        self.roles: frozenset[str] = frozenset()

    def has_capacity(self, capability: str) -> bool:
        return capability in self.capabilities


def _install_stubs() -> None:
    for name, path in (
        ("app", _BACKEND / "app"),
        ("app.core", _BACKEND / "app" / "core"),
        ("app.services", _BACKEND / "app" / "services"),
    ):
        pkg = types.ModuleType(name)
        pkg.__path__ = [str(path)]
        sys.modules.setdefault(name, pkg)

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

    errors = types.ModuleType("app.core.errors")
    errors.APIError = _APIError  # type: ignore[attr-defined]
    errors.build_error_body = lambda code, message: {"error": {"code": code, "message": message}}  # type: ignore[attr-defined]
    sys.modules["app.core.errors"] = errors

    metrics = types.ModuleType("app.core.metrics")
    metrics.AUTHORIZATION_TOTAL = _Counter()  # type: ignore[attr-defined]
    sys.modules["app.core.metrics"] = metrics

    capacity = types.ModuleType("app.services.capacity")
    capacity.OperatorIdentity = _Operator  # type: ignore[attr-defined]
    capacity.CAP_DASH_VIEW_LIVE = "dash.view.live"  # type: ignore[attr-defined]
    capacity.CAP_DASH_VIEW_HISTORY = "dash.view.history"  # type: ignore[attr-defined]
    capacity.CAP_DASH_EXPORT_CSV = "dash.export.csv"  # type: ignore[attr-defined]
    capacity.CAP_AUDIT_VIEW = "audit.view"  # type: ignore[attr-defined]
    capacity.CAP_PLATFORM_MANAGE_WEBHOOK = "platform.manage_webhook"  # type: ignore[attr-defined]
    capacity.CAP_PLATFORM_MANAGE_USERS = "platform.manage_users"  # type: ignore[attr-defined]

    def _require(capability: str, identity: Any) -> None:
        if not identity.has_capacity(capability):
            raise _APIError(403, "CAPACIDAD_DENEGADA", "denegado")

    capacity.require_capacity = _require  # type: ignore[attr-defined]

    async def _resolve(headers: Any, session: Any = None) -> Any:
        return _Operator("op", {"dash.view.live"})

    capacity.resolve_operator_identity = _resolve  # type: ignore[attr-defined]
    sys.modules["app.services.capacity"] = capacity

    audit = types.ModuleType("app.services.audit")

    async def _record_audit(**_: Any) -> None:
        return None

    audit.record_audit = _record_audit  # type: ignore[attr-defined]
    sys.modules["app.services.audit"] = audit


def _load(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


_install_stubs()
rbac = _load("app.core.rbac", _BACKEND / "app" / "core" / "rbac.py")


class _InnerApp:
    def __init__(self) -> None:
        self.called = False

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        self.called = True
        await send({"type": "http.response.start", "status": 200})


async def _no_receive() -> dict[str, Any]:
    return {"type": "http.request"}


def _scope(method: str, path: str) -> dict[str, Any]:
    return {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [(b"x-user-sub", b"op")],
        "client": ("203.0.113.5", 1234),
    }


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# =============================================================================
# Políticas
# =============================================================================
def test_policies_map_capabilities() -> None:
    policies = {f"{p.method} {p.pattern.pattern}": p for p in rbac.build_default_policies()}
    assert (
        rbac.RBACMiddleware(_InnerApp()).match("GET", "/api/v1/dashboard/snapshot").capability
        == "dash.view.live"
    )
    assert (
        rbac.RBACMiddleware(_InnerApp()).match("GET", "/api/v1/audit/events").capability
        == "audit.view"
    )
    assert (
        rbac.RBACMiddleware(_InnerApp()).match("POST", "/api/v1/admin/users").capability
        == "platform.manage_users"
    )
    assert policies  # no vacío


def test_webhook_is_signature_authenticated() -> None:
    policy = rbac.RBACMiddleware(_InnerApp()).match("POST", "/api/v1/ingest/webhook")
    assert policy is not None and policy.kind == rbac.SIGNATURE


def test_unmapped_api_route_denies_by_default() -> None:
    assert rbac.RBACMiddleware(_InnerApp()).match("GET", "/api/v1/inexistente") is None


# =============================================================================
# Comportamiento del middleware
# =============================================================================
def _invoke(middleware: Any, method: str, path: str) -> tuple[int | None, bool]:
    inner_called = middleware._inner_called
    sent: dict[str, Any] = {}

    async def _send(message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            sent["status"] = message["status"]

    _run(middleware(_scope(method, path), _no_receive, _send))
    return sent.get("status"), inner_called()


def test_middleware_allows_when_capability_present() -> None:
    inner = _InnerApp()
    mw = rbac.RBACMiddleware(
        inner,
        authorizer=lambda headers: _resolved({"dash.view.live"}),
    )
    mw._inner_called = lambda: inner.called
    status, called = _invoke(mw, "GET", "/api/v1/dashboard/snapshot")
    assert status == 200 and called is True


def test_middleware_denies_without_capability() -> None:
    inner = _InnerApp()
    mw = rbac.RBACMiddleware(
        inner,
        authorizer=lambda headers: _resolved(set()),
    )
    mw._inner_called = lambda: inner.called
    status, called = _invoke(mw, "GET", "/api/v1/dashboard/snapshot")
    assert status == 403 and called is False


def test_middleware_denies_unmapped_route() -> None:
    inner = _InnerApp()
    mw = rbac.RBACMiddleware(inner, authorizer=lambda headers: _resolved({"dash.view.live"}))
    mw._inner_called = lambda: inner.called
    status, called = _invoke(mw, "GET", "/api/v1/desconocido")
    assert status == 403 and called is False


def test_middleware_skips_signature_route() -> None:
    inner = _InnerApp()
    mw = rbac.RBACMiddleware(inner, authorizer=lambda headers: _resolved(set()))
    mw._inner_called = lambda: inner.called
    status, called = _invoke(mw, "POST", "/api/v1/ingest/webhook")
    assert status == 200 and called is True


async def _resolved(caps: set[str]) -> _Operator:
    return _Operator("op", caps)


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
