"""Test unitario de la verificación de firma HMAC-SHA256 del webhook (T22, §9.2).

Cubre:

- Vector HMAC-SHA256 conocido (RFC 4231, Test Case 2).
- Construcción exacta de la cadena canónica §9.2.
- Verificación correcta (identidad + ``key_id``) y rechazo por cuerpo alterado.
- ``key_id`` no vigente ⇒ ``403`` (fail-closed).
- Solape de rotación de 24 h: dos ``key_id`` válidos a la vez; la versión
  saliente deja de aceptarse al cerrar su ventana.
- Formato de cabeceras y decodificación del material del secreto.
- Resolución del secreto desde el secret manager en runtime (``WEBHOOK_SECRETS``).

Se puede ejecutar con pytest o directamente::

    py backend/tests/test_webhook_signature.py

En entornos sin dependencias (fastapi/pydantic) el cargador instala *stubs*
mínimos para poder ejercer la primitiva aislada.
"""

from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import logging
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# Vector conocido RFC 4231 Test Case 2.
_RFC4231_KEY = b"Jefe"
_RFC4231_DATA = "what do ya want for nothing?"
_RFC4231_HMAC = "5bdcc146bf60754e6a042426089575c75a003f089d2739839dec58b964ec3843"


def _load_with_stubs() -> types.ModuleType:
    """Carga ``webhook_signature`` con stubs si faltan dependencias externas."""
    for name, path in (
        ("app", _BACKEND / "app"),
        ("app.core", _BACKEND / "app" / "core"),
        ("app.services", _BACKEND / "app" / "services"),
    ):
        pkg = types.ModuleType(name)
        pkg.__path__ = [str(path)]
        sys.modules.setdefault(name, pkg)

    class _StubSettings:
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

    _status = {"UNAUTHORIZED": 401, "KEY_NOT_ACTIVE": 403, "UNAVAILABLE": 503}

    def _raise(code: str, message: str, *, status_code: int | None = None) -> Any:
        raise _StubAPIError(status_code or _status.get(code, 500), code, message)

    errors_mod = types.ModuleType("app.core.errors")
    errors_mod.APIError = _StubAPIError  # type: ignore[attr-defined]
    errors_mod.raise_http_error = _raise  # type: ignore[attr-defined]
    sys.modules["app.core.errors"] = errors_mod

    logging_mod = types.ModuleType("app.core.logging")
    logging_mod.get_logger = logging.getLogger  # type: ignore[attr-defined]
    sys.modules["app.core.logging"] = logging_mod

    spec = importlib.util.spec_from_file_location(
        "app.services.webhook_signature",
        _BACKEND / "app" / "services" / "webhook_signature.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["app.services.webhook_signature"] = module
    spec.loader.exec_module(module)
    return module


def _load_module() -> types.ModuleType:
    try:
        import pydantic_settings  # noqa: F401
        import starlette  # noqa: F401
        from app.services import webhook_signature

        return webhook_signature
    except ImportError:
        return _load_with_stubs()


ws = _load_module()

_WEBHOOK_ID = "wh-sifcop-central"
_KEY_ID = "wk-2026-10"
_NONCE = "7f3c9a2b1d8e4c6f5a0b3d9e8c7f6a1b"
_TS = "2026-10-03T14:22:05Z"
_VERSION = "1.0.0"
_SECRET = bytes(range(32))


class _FakeSecretManager:
    def __init__(self, secrets: dict[tuple[str, str], bytes]) -> None:
        self._secrets = secrets

    def get_webhook_secret(self, *, webhook_id: str, key_id: str) -> bytes | None:
        return self._secrets.get((webhook_id, key_id))


def _metadata(key_id: str = _KEY_ID, **kwargs: Any) -> Any:
    return ws.WebhookSecretMetadata(
        key_id=key_id, webhook_id=_WEBHOOK_ID, estado="vigente", **kwargs
    )


def _headers(
    body: bytes, secret: bytes = _SECRET, *, key_id: str = _KEY_ID, **overrides: str
) -> dict[str, str]:
    content = hashlib.sha256(body).hexdigest()
    canonical = ws.build_canonical_string(
        webhook_id=_WEBHOOK_ID,
        key_id=key_id,
        nonce=_NONCE,
        timestamp=_TS,
        schema_version=_VERSION,
        content_sha256=content,
    )
    signature = ws.compute_signature_hex(secret, canonical)
    headers = {
        ws.WEBHOOK_ID_HEADER: _WEBHOOK_ID,
        ws.KEY_ID_HEADER: key_id,
        ws.NONCE_HEADER: _NONCE,
        ws.TIMESTAMP_HEADER: _TS,
        ws.VERSION_HEADER: _VERSION,
        ws.SIGNATURE_HEADER: f"sha256={signature}",
    }
    headers.update(overrides)
    return headers


def _verify(body: bytes, headers: dict[str, str], metadata_candidates: Any, secrets: Any) -> Any:
    return ws.verify_webhook_signature(
        body=body,
        headers=headers,
        metadata_candidates=metadata_candidates,
        secret_manager=_FakeSecretManager(secrets),
    )


def _expect_reject(callable_: Any) -> Any:
    try:
        callable_()
    except Exception as exc:  # noqa: BLE001 - se inspecciona el código de rechazo
        return exc
    raise AssertionError("se esperaba un rechazo (fail-closed) y no ocurrió")


def test_rfc4231_vector() -> None:
    assert ws.compute_signature_hex(_RFC4231_KEY, _RFC4231_DATA) == _RFC4231_HMAC


def test_canonical_string_exact() -> None:
    canonical = ws.build_canonical_string(
        webhook_id="wh-1",
        key_id="wk-1",
        nonce="ab" * 16,
        timestamp="2026-10-03T14:22:05Z",
        schema_version="1.0.0",
        content_sha256="deadbeef",
    )
    assert canonical == f"wh-1|wk-1|{'ab' * 16}|2026-10-03T14:22:05Z|1.0.0|deadbeef"


def test_verify_ok_returns_identity_and_key_id() -> None:
    body = b'{"event_id":"e1"}'
    result = _verify(
        body,
        _headers(body),
        [_metadata()],
        {(_WEBHOOK_ID, _KEY_ID): _SECRET},
    )
    assert result.webhook_id == _WEBHOOK_ID
    assert result.key_id == _KEY_ID
    assert result.nonce == _NONCE
    assert result.content_sha256 == hashlib.sha256(body).hexdigest()


def test_tampered_body_rejected() -> None:
    headers = _headers(b'{"event_id":"e1"}')
    exc = _expect_reject(
        lambda: _verify(
            b'{"event_id":"e2"}',
            headers,
            [_metadata()],
            {(_WEBHOOK_ID, _KEY_ID): _SECRET},
        )
    )
    assert getattr(exc, "code", "") == "UNAUTHORIZED"


def test_wrong_secret_rejected() -> None:
    body = b"{}"
    exc = _expect_reject(
        lambda: _verify(
            body,
            _headers(body, secret=b"x" * 32),
            [_metadata()],
            {(_WEBHOOK_ID, _KEY_ID): _SECRET},
        )
    )
    assert getattr(exc, "code", "") == "UNAUTHORIZED"


def test_key_id_not_active_rejected() -> None:
    body = b"{}"
    exc = _expect_reject(
        lambda: _verify(
            body,
            _headers(body),
            [_metadata(key_id="wk-other")],
            {(_WEBHOOK_ID, _KEY_ID): _SECRET},
        )
    )
    assert getattr(exc, "code", "") == "KEY_NOT_ACTIVE"


def test_rotation_overlap_two_keys_valid() -> None:
    now = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)
    body = b'{"event_id":"e1"}'
    old_secret, new_secret = b"a" * 32, b"b" * 32
    candidates = [
        ws.WebhookSecretMetadata(
            key_id="wk-old",
            webhook_id=_WEBHOOK_ID,
            estado="vigente",
            not_after=now + timedelta(hours=12),  # solape hasta +12 h
        ),
        ws.WebhookSecretMetadata(
            key_id="wk-new",
            webhook_id=_WEBHOOK_ID,
            estado="vigente",
            not_before=now - timedelta(hours=12),
        ),
    ]
    secrets = {(_WEBHOOK_ID, "wk-old"): old_secret, (_WEBHOOK_ID, "wk-new"): new_secret}

    for key_id, secret in (("wk-old", old_secret), ("wk-new", new_secret)):
        result = ws.verify_webhook_signature(
            body=body,
            headers=_headers(body, secret, key_id=key_id),
            metadata_candidates=candidates,
            secret_manager=_FakeSecretManager(secrets),
            now=now,
        )
        assert result.key_id == key_id

    # Fuera del solape, la versión saliente deja de ser válida.
    exc = _expect_reject(
        lambda: ws.verify_webhook_signature(
            body=body,
            headers=_headers(body, old_secret, key_id="wk-old"),
            metadata_candidates=candidates,
            secret_manager=_FakeSecretManager(secrets),
            now=now + timedelta(hours=13),
        )
    )
    assert getattr(exc, "code", "") == "KEY_NOT_ACTIVE"


def test_malformed_signature_header_rejected() -> None:
    body = b"{}"
    headers = _headers(body)
    headers[ws.SIGNATURE_HEADER] = "md5=1234"
    exc = _expect_reject(lambda: _verify(body, headers, [_metadata()], {}))
    assert getattr(exc, "code", "") == "UNAUTHORIZED"


def test_missing_header_rejected() -> None:
    body = b"{}"
    headers = _headers(body)
    del headers[ws.NONCE_HEADER]
    exc = _expect_reject(lambda: _verify(body, headers, [_metadata()], {}))
    assert getattr(exc, "code", "") == "UNAUTHORIZED"


def test_secret_missing_from_secret_manager_is_unavailable() -> None:
    body = b"{}"
    exc = _expect_reject(lambda: _verify(body, _headers(body), [_metadata()], {}))
    assert getattr(exc, "code", "") == "UNAVAILABLE"


def test_decode_secret_material_hex_and_base64() -> None:
    raw = bytes(range(32))
    assert ws.decode_secret_material(raw.hex()) == raw
    assert ws.decode_secret_material(base64.b64encode(raw).decode()) == raw


def test_environment_secret_manager_reads_injected_map() -> None:
    raw = bytes(range(32))
    environ = {"WEBHOOK_SECRETS": json.dumps({f"{_WEBHOOK_ID}:{_KEY_ID}": raw.hex()})}
    settings = types.SimpleNamespace(webhook_id="", webhook_key_id="", webhook_secret="")
    manager = ws.EnvironmentSecretManager(settings=settings, environ=environ)
    assert manager.get_webhook_secret(webhook_id=_WEBHOOK_ID, key_id=_KEY_ID) == raw


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
