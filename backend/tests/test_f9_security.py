"""T70 — Pruebas de seguridad (RNF-01/AM-03/AM-06/AM-11/AM-12).

Verifica la configuración de seguridad verificable sin servidor:

- **TLS 1.3 only**: ``app/core/tls.py`` fija ``minimum_version`` y
  ``maximum_version`` a ``TLSv1_3`` (TLS 1.2 deshabilitado, OD-09/RNF-01.a).
- **HSTS + cabeceras** del borde de la SPA (``dashboard/public/_headers``):
  ``max-age=31536000; includeSubDomains; preload``, ``X-Frame-Options: DENY``,
  ``frame-ancestors 'none'`` y ``script-src`` **sin** ``unsafe-inline``.
- **CORS deny-by-default**: la allowlist de la config arranca vacía y
  ``allow_credentials`` solo se habilita con allowlist no vacía (§2.2.2).
- **Sin secretos en el origen**: ningún ``.gs`` incrusta el secreto del webhook
  (vive en ``Script Properties``, RNF-13/AM-14).

La firma del webhook (rechazo sin firma o manipulada) y el anti-replay se
prueban en ``test_f9_apps_script_webhook.py`` y ``test_replay_guard.py``; el XSS
en ``dashboard/src/test/xss.test.tsx``.

Directamente::

    py backend/tests/test_f9_security.py
"""

from __future__ import annotations

import importlib.util
import re
import ssl
import sys
import types
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1]
_REPO = _BACKEND.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))


class _StubSettings:
    tls_certfile = ""
    tls_keyfile = ""
    tls_keyfile_password = ""
    tls_ca_certs = ""


def _load_tls() -> types.ModuleType:
    try:
        from app.core import tls  # noqa: F401

        return tls
    except ImportError:
        for name, path in (
            ("app", _BACKEND / "app"),
            ("app.core", _BACKEND / "app" / "core"),
        ):
            pkg = types.ModuleType(name)
            pkg.__path__ = [str(path)]  # type: ignore[attr-defined]
            sys.modules.setdefault(name, pkg)
        config_mod = types.ModuleType("app.config")
        config_mod.Settings = _StubSettings  # type: ignore[attr-defined]
        config_mod.get_settings = lambda: _StubSettings()  # type: ignore[attr-defined]
        sys.modules["app.config"] = config_mod
        spec = importlib.util.spec_from_file_location("app.core.tls", _BACKEND / "app" / "core" / "tls.py")
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        sys.modules["app.core.tls"] = module
        getattr(spec.loader, "exec_module")(module)
        return module


tls = _load_tls()


# =============================================================================
# Casos
# =============================================================================
def test_tls_context_only_negotiates_1_3() -> None:
    context = tls.build_tls_context(_StubSettings())
    assert context.minimum_version == ssl.TLSVersion.TLSv1_3
    assert context.maximum_version == ssl.TLSVersion.TLSv1_3
    # No existe ruta que acepte TLS 1.2 (OD-09).
    assert context.minimum_version != ssl.TLSVersion.TLSv1_2


def test_spa_headers_have_hsts_and_anti_framing() -> None:
    headers = (_REPO / "dashboard" / "public" / "_headers").read_text(encoding="utf-8")
    assert "Strict-Transport-Security" in headers
    assert "max-age=31536000" in headers
    assert "includeSubDomains" in headers
    assert "preload" in headers
    assert "X-Frame-Options: DENY" in headers
    assert "frame-ancestors 'none'" in headers
    assert "Cross-Origin-Opener-Policy" in headers


def test_spa_csp_has_no_unsafe_inline_script() -> None:
    headers = (_REPO / "dashboard" / "public" / "_headers").read_text(encoding="utf-8")
    csp = next(
        (line for line in headers.splitlines() if "Content-Security-Policy" in line),
        "",
    )
    script_src = re.search(r"script-src([^;]*);", csp)
    assert script_src is not None
    assert "unsafe-inline" not in script_src.group(1)
    assert "'self'" in script_src.group(1)


def test_cors_is_deny_by_default() -> None:
    config_src = (_BACKEND / "app" / "config.py").read_text(encoding="utf-8")
    assert 'cors_allow_origins: str = ""' in config_src
    # allow_credentials solo es válido con allowlist no vacía.
    assert "return self.cors_allow_credentials and bool(self.cors_origins)" in config_src


def test_security_constants_hardened() -> None:
    src = (_BACKEND / "app" / "core" / "security.py").read_text(encoding="utf-8")
    assert 'X_FRAME_OPTIONS: Final = "DENY"' in src
    assert "frame-ancestors 'none'" in src
    assert 'CACHE_CONTROL_NO_STORE: Final = "no-store, private"' in src
    assert 'CROSS_ORIGIN_OPENER_POLICY: Final = "same-origin"' in src


def test_apps_script_never_hardcodes_webhook_secret() -> None:
    # El secreto vive en Script Properties; ningún .gs debe contener un literal
    # de 64 hex (material del secreto) ni la cabecera de firma hardcodeada.
    for path in (_REPO / "apps-script").glob("*.gs"):
        source = path.read_text(encoding="utf-8")
        assert not re.search(r"['\"][0-9a-fA-F]{64}['\"]", source), path.name
    credentials = (_REPO / "apps-script" / "20_credentials.gs").read_text(encoding="utf-8")
    assert "Script" in credentials and "Properties" in credentials


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
