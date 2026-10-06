"""T65 — Verificación del webhook firmado de Apps Script / integración Google Sheets.

Replica la firma que produce ``apps-script/50_signer.gs`` a partir del cuerpo
canónico §9.2 y comprueba la primitiva de verificación del backend. Es la
prueba de **interoperabilidad** entre el origen (Google Apps Script) y el
backend FastAPI:

- La cadena canónica de Apps Script coincide **exactamente** con
  ``build_canonical_string`` (``webhook_id|key_id|nonce|timestamp|version|sha256``).
- La firma HMAC-SHA256 de Apps Script (``Utilities.computeHmacSha256Signature``
  sobre bytes del secreto) coincide con ``compute_signature_hex``.
- Un mensaje firmado válido → identidad (``webhook_id``/``key_id``/``nonce``).
- Cuerpo **alterado** tras firmar → ``401`` (CA-01.3, fail-closed).
- Cuerpo **no-JSON** correctamente firmado → se verifica sin deserializar
  (CA-01.2: la autenticación precede al parseo).
- Sin cabecera ``X-Webhook-Signature`` → ``401``.

Se carga con *stubs* mínimos si faltan dependencias. Directamente::

    py backend/tests/test_f9_apps_script_webhook.py
"""

from __future__ import annotations

import hashlib
import hmac
import importlib.util
import logging
import sys
import types
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_WEBHOOK_ID = "wh-sifcop-central"
_KEY_ID = "wk-2026-10"
_NONCE = "7f3c9a2b1d8e4c6f5a0b3d9e8c7f6a1b"
_TS = "2026-10-03T14:22:05Z"
_VERSION = "1.0.0"
_SECRET = bytes(range(32))


class _StubSettings:
    webhook_id = ""
    webhook_key_id = ""
    webhook_secret = ""


class _StubAPIError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code


_STATUS = {"UNAUTHORIZED": 401, "KEY_NOT_ACTIVE": 403, "UNAVAILABLE": 503}


def _raise(code: str, message: str, *, status_code: int | None = None) -> Any:
    raise _StubAPIError(status_code or _STATUS.get(code, 500), code, message)


def _install_stubs() -> None:
    for name, path in (
        ("app", _BACKEND / "app"),
        ("app.core", _BACKEND / "app" / "core"),
        ("app.services", _BACKEND / "app" / "services"),
    ):
        pkg = types.ModuleType(name)
        pkg.__path__ = [str(path)]  # type: ignore[attr-defined]
        sys.modules.setdefault(name, pkg)

    config_mod = types.ModuleType("app.config")
    config_mod.Settings = _StubSettings  # type: ignore[attr-defined]
    config_mod.get_settings = lambda: _StubSettings()  # type: ignore[attr-defined]
    sys.modules["app.config"] = config_mod

    errors_mod = types.ModuleType("app.core.errors")
    errors_mod.APIError = _StubAPIError  # type: ignore[attr-defined]
    errors_mod.raise_http_error = _raise  # type: ignore[attr-defined]
    sys.modules["app.core.errors"] = errors_mod

    logging_mod = types.ModuleType("app.core.logging")
    logging_mod.get_logger = logging.getLogger  # type: ignore[attr-defined]
    sys.modules["app.core.logging"] = logging_mod


def _load() -> types.ModuleType:
    try:
        from app.services import webhook_signature  # noqa: F401

        return webhook_signature
    except ImportError:
        _install_stubs()
        spec = importlib.util.spec_from_file_location(
            "app.services.webhook_signature",
            _BACKEND / "app" / "services" / "webhook_signature.py",
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules["app.services.webhook_signature"] = module
        getattr(spec.loader, "exec_module")(module)
        return module


ws = _load()


# =============================================================================
# Simulación del origen (Apps Script 50_signer.gs)
# =============================================================================
def apps_script_canonical(body: bytes, *, key_id: str = _KEY_ID, nonce: str = _NONCE) -> str:
    """``buildCanonicalString_`` de ``apps-script/50_signer.gs``."""
    return "|".join(
        [
            _WEBHOOK_ID,
            key_id,
            nonce,
            _TS,
            _VERSION,
            hashlib.sha256(body).hexdigest(),
        ]
    )


def apps_script_signature(body: bytes, secret: bytes = _SECRET) -> str:
    """``computeSignatureHeader_``: ``sha256=`` + HMAC-SHA256 hex."""
    digest = hmac.new(secret, apps_script_canonical(body).encode("utf-8"), hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def _headers(body: bytes, *, secret: bytes = _SECRET, **overrides: str) -> dict[str, str]:
    headers = {
        ws.WEBHOOK_ID_HEADER: _WEBHOOK_ID,
        ws.KEY_ID_HEADER: _KEY_ID,
        ws.NONCE_HEADER: _NONCE,
        ws.TIMESTAMP_HEADER: _TS,
        ws.VERSION_HEADER: _VERSION,
        ws.SIGNATURE_HEADER: apps_script_signature(body, secret),
    }
    headers.update(overrides)
    return headers


class _FakeSecretManager:
    def __init__(self, secrets: dict[tuple[str, str], bytes]) -> None:
        self._secrets = secrets

    def get_webhook_secret(self, *, webhook_id: str, key_id: str) -> bytes | None:
        return self._secrets.get((webhook_id, key_id))


def _metadata() -> Any:
    return ws.WebhookSecretMetadata(
        key_id=_KEY_ID, webhook_id=_WEBHOOK_ID, estado="vigente"
    )


def _verify(body: bytes, headers: dict[str, str]) -> Any:
    return ws.verify_webhook_signature(
        body=body,
        headers=headers,
        metadata_candidates=[_metadata()],
        secret_manager=_FakeSecretManager({(_WEBHOOK_ID, _KEY_ID): _SECRET}),
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
def test_apps_script_canonical_matches_backend() -> None:
    body = b'{"event_id":"018f1d2e-3a4b-7c5d-8e6f-0a1b2c3d4e5f"}'
    assert apps_script_canonical(body) == ws.build_canonical_string(
        webhook_id=_WEBHOOK_ID,
        key_id=_KEY_ID,
        nonce=_NONCE,
        timestamp=_TS,
        schema_version=_VERSION,
        content_sha256=hashlib.sha256(body).hexdigest(),
    )


def test_apps_script_signature_matches_backend() -> None:
    body = b'{"event_id":"e1"}'
    expected = apps_script_signature(body).removeprefix("sha256=")
    assert ws.compute_signature_hex(_SECRET, apps_script_canonical(body)) == expected


def test_valid_apps_script_webhook_is_verified() -> None:
    body = b'{"event_id":"018f1d2e-3a4b-7c5d-8e6f-0a1b2c3d4e5f"}'
    identity = _verify(body, _headers(body))
    assert identity.webhook_id == _WEBHOOK_ID
    assert identity.key_id == _KEY_ID
    assert identity.nonce == _NONCE
    assert identity.content_sha256 == hashlib.sha256(body).hexdigest()


def test_tampered_body_rejected_401() -> None:
    original = b'{"event_id":"e1","value":1}'
    headers = _headers(original)
    tampered = b'{"event_id":"e1","value":999}'
    exc = _expect_reject(lambda: _verify(tampered, headers))
    assert getattr(exc, "code", "") == "UNAUTHORIZED"
    assert getattr(exc, "status_code", 0) == 401


def test_non_json_body_verified_without_deserializing() -> None:
    # La autenticación del webhook no interpreta el cuerpo: bytes no-JSON pero
    # correctamente firmados superan la verificación (el parseo es posterior).
    body = b"esto-no-es-json{{{{"
    identity = _verify(body, _headers(body))
    assert identity.webhook_id == _WEBHOOK_ID


def test_missing_signature_header_rejected_401() -> None:
    body = b"{}"
    headers = _headers(body)
    del headers[ws.SIGNATURE_HEADER]
    exc = _expect_reject(lambda: _verify(body, headers))
    assert getattr(exc, "code", "") == "UNAUTHORIZED"


def test_wrong_secret_rejected_401() -> None:
    body = b"{}"
    exc = _expect_reject(lambda: _verify(body, _headers(body, secret=b"x" * 32)))
    assert getattr(exc, "code", "") == "UNAUTHORIZED"


def test_content_hash_dedup_is_stable() -> None:
    # CA-01.4: la deduplicación por contenido usa `content_sha256` del contenido
    # normalizado; idéntico contenido → mismo hash (no se envía), distinto → cambia.
    normalized = b'{"schema_version":"1.0.0","data_date":"2026-10-03","grid":[[1,2]]}'
    identical = b'{"schema_version":"1.0.0","data_date":"2026-10-03","grid":[[1,2]]}'
    changed = b'{"schema_version":"1.0.0","data_date":"2026-10-03","grid":[[1,3]]}'
    assert hashlib.sha256(normalized).hexdigest() == hashlib.sha256(identical).hexdigest()
    assert hashlib.sha256(normalized).hexdigest() != hashlib.sha256(changed).hexdigest()
    # El origen compara contra el último hash exitoso antes de transmitir.
    digest = (_BACKEND.parent / "apps-script" / "40_digest.gs").read_text(encoding="utf-8")
    assert "hasContentChanged_" in digest and "contentSha256_" in digest


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
