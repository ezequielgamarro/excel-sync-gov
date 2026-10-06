"""T65 — RBAC por capacidad sobre el JWT nativo (RNF-03.a/b/c, CA-02.9, §2.2.3).

Encadena la autenticación nativa (JWT firmado por el backend) con la resolución
de capacidades del operador y la comprobación fail-closed:

- Un token válido con `dash.view.live` resuelve la identidad y autoriza la
  capacidad.
- Un token válido **sin** `audit.view` → ``403`` al exigirla.
- Token con firma manipulada / expirado → ``401``.
- El mapeo rol→capacidad de la tabla local se combina con las capacidades del
  token (deny por defecto).

Se carga `app.services.capacity`/`jwt_native` con *stubs* mínimos. Directamente::

    py backend/tests/test_f9_rbac_jwt.py
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

_ISSUER = "excel-sync-gov-backend"
_AUDIENCE = "dashboard-api"
_SECRET = "clave-de-firma-de-prueba"


class _APIError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code


class _Result:
    def __init__(self, rows: list[tuple[str, ...]]) -> None:
        self._rows = rows

    def __iter__(self) -> Any:
        return iter(self._rows)


class _FakeSession:
    """Sesión SQLAlchemy mínima que devuelve capacidades por rol."""

    def __init__(self, rows: list[tuple[str, ...]]) -> None:
        self._rows = rows

    async def execute(self, _statement: Any) -> _Result:
        return _Result(self._rows)


class _Column:
    def in_(self, *_: Any) -> "_Column":
        return self

    def is_(self, *_: Any) -> "_Column":
        return self


class _Table:
    def __init__(self, columns: tuple[str, ...]) -> None:
        self.c = types.SimpleNamespace(**{column: _Column() for column in columns})


class _SelectChain:
    def where(self, *_: Any) -> "_SelectChain":
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
        jwt_issuer = _ISSUER
        jwt_audience = _AUDIENCE
        jwt_signing_key = _SECRET
        jwt_algorithm = "HS256"
        jwt_access_token_ttl_seconds = 900
        jwt_clock_skew_seconds = 0

    config_mod = types.ModuleType("app.config")
    config_mod.Settings = _Settings  # type: ignore[attr-defined]
    config_mod.get_settings = lambda: _Settings()  # type: ignore[attr-defined]
    sys.modules["app.config"] = config_mod

    errors_mod = types.ModuleType("app.core.errors")
    errors_mod.APIError = _APIError  # type: ignore[attr-defined]

    def _raise(code: str, message: str, *, status_code: int | None = None) -> Any:
        status = status_code or {"UNAUTHORIZED": 401, "CAPACIDAD_DENEGADA": 403}.get(code, 500)
        raise _APIError(status, code, message)

    errors_mod.raise_http_error = _raise  # type: ignore[attr-defined]
    sys.modules["app.core.errors"] = errors_mod

    logging_mod = types.ModuleType("app.core.logging")
    logging_mod.get_logger = logging.getLogger  # type: ignore[attr-defined]
    sys.modules["app.core.logging"] = logging_mod

    tables_mod = types.ModuleType("app.models.tables")
    tables_mod.role_capability = _Table(("capability", "role", "granted"))  # type: ignore[attr-defined]
    sys.modules["app.models.tables"] = tables_mod

    sqlalchemy_mod = types.ModuleType("sqlalchemy")
    sqlalchemy_mod.select = lambda *_a, **_k: _SelectChain()  # type: ignore[attr-defined]
    ext_mod = types.ModuleType("sqlalchemy.ext")
    asyncio_mod = types.ModuleType("sqlalchemy.ext.asyncio")
    asyncio_mod.AsyncSession = object  # type: ignore[attr-defined]
    sys.modules["sqlalchemy"] = sqlalchemy_mod
    sys.modules["sqlalchemy.ext"] = ext_mod
    sys.modules["sqlalchemy.ext.asyncio"] = asyncio_mod

    fastapi_mod = types.ModuleType("fastapi")
    fastapi_mod.Depends = lambda dependency=None: dependency  # type: ignore[attr-defined]

    class _Request:
        pass

    fastapi_mod.Request = _Request  # type: ignore[attr-defined]
    sys.modules["fastapi"] = fastapi_mod

    db_mod = types.ModuleType("app.services.db")

    async def _session_dependency() -> Any:  # pragma: no cover - solo DI
        yield _FakeSession([])

    db_mod.session_dependency = _session_dependency  # type: ignore[attr-defined]
    sys.modules["app.services.db"] = db_mod


def _load(name: str, path: Path) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _load_modules() -> tuple[types.ModuleType, types.ModuleType]:
    try:
        from app.services import capacity, jwt_native  # noqa: F401

        return capacity, jwt_native
    except ImportError:
        _install_stubs()
        jwt_native = _load(
            "app.services.jwt_native", _BACKEND / "app" / "services" / "jwt_native.py"
        )
        capacity = _load("app.services.capacity", _BACKEND / "app" / "services" / "capacity.py")
        return capacity, jwt_native


capacity, jwt_native = _load_modules()

# Fuerza la configuración de firma de prueba tanto en el camino con *stubs*
# como con las dependencias reales instaladas (`get_settings()` leería el
# entorno, que puede no tener `JWT_SIGNING_KEY`).
_JWT_SETTINGS = types.SimpleNamespace(
    jwt_issuer=_ISSUER,
    jwt_audience=_AUDIENCE,
    jwt_signing_key=_SECRET,
    jwt_algorithm="HS256",
    jwt_access_token_ttl_seconds=900,
    jwt_clock_skew_seconds=0,
)
capacity.get_settings = lambda: _JWT_SETTINGS  # type: ignore[attr-defined]
capacity.reset_jwt_service()


def _sign(capabilities: list[str], roles: list[str] | None = None) -> str:
    service = jwt_native.NativeJwtService(
        jwt_native.NativeJwtConfig(
            issuer=_ISSUER,
            audience=_AUDIENCE,
            signing_key=_SECRET,
            algorithm="HS256",
            access_token_ttl_seconds=900,
            clock_skew_seconds=0,
        )
    )
    token: str = service.issue_access_token(
        sub="operador-1", roles=roles or ["viewer"], capabilities=capabilities
    )
    return token


def _resolve(token: str, *, role_rows: list[tuple[str, ...]] | None = None) -> Any:
    capacity.reset_jwt_service()
    session = _FakeSession(role_rows if role_rows is not None else [("dash.view.live",)])
    headers = {"Authorization": f"Bearer {token}"}
    return asyncio.run(capacity.resolve_operator_identity(headers, session))


def _expect_reject(coro: Any) -> Any:
    try:
        asyncio.run(coro)
    except Exception as exc:  # noqa: BLE001
        return exc
    raise AssertionError("se esperaba un rechazo (fail-closed) y no ocurrió")


# =============================================================================
# Casos
# =============================================================================
def test_valid_jwt_grants_embedded_capability() -> None:
    identity = _resolve(_sign(["dash.view.live"]), role_rows=[])
    assert identity.sub == "operador-1"
    assert identity.has_capacity("dash.view.live")
    capacity.require_capacity("dash.view.live", identity)  # no lanza


def test_role_capability_table_grants_capability() -> None:
    # El token no trae capacidades; el mapeo rol→capacidad de la tabla las aporta.
    identity = _resolve(_sign([]), role_rows=[("dash.view.live",), ("dash.export.csv",)])
    assert identity.has_capacity("dash.export.csv")


def test_missing_capability_is_denied_403() -> None:
    identity = _resolve(_sign(["dash.view.live"]), role_rows=[])
    exc = _expect_reject(_async_require("audit.view", identity))
    assert getattr(exc, "status_code", 0) == 403
    assert getattr(exc, "code", "") == "CAPACIDAD_DENEGADA"


async def _async_require(capability: str, identity: Any) -> None:
    capacity.require_capacity(capability, identity)


def test_unknown_capabilities_are_filtered_out() -> None:
    identity = _resolve(_sign(["dash.view.live", "capacidad.inventada"]), role_rows=[])
    assert identity.has_capacity("dash.view.live")
    assert not identity.has_capacity("capacidad.inventada")


def test_tampered_token_is_rejected_401() -> None:
    token = _sign(["dash.view.live"])
    tampered = token[:-2] + ("aa" if token[-2:] != "aa" else "bb")
    exc = _expect_reject(
        capacity.resolve_operator_identity(
            {"Authorization": f"Bearer {tampered}"}, _FakeSession([])
        )
    )
    assert getattr(exc, "status_code", 0) == 401


def test_missing_bearer_is_rejected_401() -> None:
    exc = _expect_reject(capacity.resolve_operator_identity({}, _FakeSession([])))
    assert getattr(exc, "status_code", 0) == 401


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
