"""Tests de la auth nativa JWT y el refresh rotativo (T35, §2.2.2).

Sin dependencias externas (solo stdlib): se prueban la emisión/validación de JWT
propios (iss/aud/exp/nbf/jti, vida ≤ 15 min, firma), la rotación con detección de
reutilización del refresh y la política mínima de contraseñas.

    py backend/tests/test_jwt_native_f5.py
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services.jwt_native import (  # noqa: E402
    AccessTokenClaims,
    NativeJwtConfig,
    NativeJwtService,
    RefreshRotationService,
    TokenError,
)
from app.services.passwords import (  # noqa: E402
    PasswordPolicy,
    PasswordPolicyError,
    validate_password_policy,
)

_NOW = 1_760_000_000
_ISSUER = "excel-sync-gov-backend"
_AUDIENCE = "dashboard-api"
_SECRET = "test-signing-key-not-a-real-secret"


def _service(**overrides: Any) -> NativeJwtService:
    base = dict(
        issuer=_ISSUER,
        audience=_AUDIENCE,
        signing_key=_SECRET,
        algorithm="HS256",
        access_token_ttl_seconds=900,
        clock_skew_seconds=0,
    )
    base.update(overrides)
    return NativeJwtService(NativeJwtConfig(**base), clock=lambda: float(_NOW))


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


# =============================================================================
# JWT nativo
# =============================================================================
def test_issued_token_roundtrips_claims() -> None:
    service = _service()
    token = service.issue_access_token(
        sub="user-1", roles=["supervisor"], capabilities=["dash.view.live"]
    )
    claims = service.validate_access_token(token)
    assert isinstance(claims, AccessTokenClaims)
    assert claims.sub == "user-1"
    assert claims.roles == frozenset({"supervisor"})
    assert claims.capabilities == frozenset({"dash.view.live"})
    assert claims.expires_at - claims.issued_at == 900


def test_bad_signature_is_rejected() -> None:
    token = _service(signing_key="otra-clave").issue_access_token(sub="user-1")
    try:
        _service().validate_access_token(token)
    except TokenError as exc:
        assert exc.reason == "bad_signature"
    else:  # pragma: no cover
        raise AssertionError("firma inválida debía rechazarse")


def test_algorithm_is_pinned() -> None:
    token = _service(algorithm="HS256").issue_access_token(sub="user-1")
    try:
        _service(algorithm="RS256").validate_access_token(token)
    except TokenError as exc:
        assert exc.reason == "alg_not_allowed"
    else:  # pragma: no cover
        raise AssertionError("algoritmo distinto debía rechazarse")


def test_expired_token_is_rejected() -> None:
    token = _service().issue_access_token(sub="user-1", now=_NOW - 10_000)
    try:
        _service().validate_access_token(token)
    except TokenError as exc:
        assert exc.reason == "expired"
    else:  # pragma: no cover
        raise AssertionError("token expirado debía rechazarse")


def test_wrong_issuer_and_audience_are_rejected() -> None:
    for overrides, reason in (
        ({"issuer": "otro-emisor"}, "bad_issuer"),
        ({"audience": "otra-api"}, "bad_audience"),
    ):
        token = _service(issuer=_ISSUER, audience=_AUDIENCE).issue_access_token(sub="u")
        try:
            _service(**overrides).validate_access_token(token)
        except TokenError as exc:
            assert exc.reason == reason
        else:  # pragma: no cover
            raise AssertionError(f"{reason} debía rechazarse")


def test_lifetime_over_15_minutes_is_rejected() -> None:
    token = _service(access_token_ttl_seconds=1800).issue_access_token(sub="u")
    try:
        _service().validate_access_token(token)
    except TokenError as exc:
        assert exc.reason == "token_lifetime_too_long"
    else:  # pragma: no cover
        raise AssertionError("vida > 15 min debía rechazarse")


def test_token_without_jti_is_rejected() -> None:
    service = _service()
    payload = {
        "iss": _ISSUER,
        "aud": _AUDIENCE,
        "sub": "u",
        "iat": _NOW,
        "nbf": _NOW,
        "exp": _NOW + 900,
        "roles": [],
        "capabilities": [],
    }
    token = service._sign({"alg": "HS256", "typ": "JWT"}, payload)  # noqa: SLF001
    try:
        service.validate_access_token(token)
    except TokenError as exc:
        assert exc.reason == "missing_jti"
    else:  # pragma: no cover
        raise AssertionError("token sin jti debía rechazarse")


def test_issue_without_signing_key_fails_closed() -> None:
    try:
        _service(signing_key="").issue_access_token(sub="u")
    except TokenError as exc:
        assert exc.reason == "signing_key_missing"
    else:  # pragma: no cover
        raise AssertionError("sin clave de firma debía fallar")


# =============================================================================
# Refresh rotativo con detección de reutilización
# =============================================================================
def test_refresh_rotation_issues_new_tokens() -> None:
    service = RefreshRotationService(clock=lambda: float(_NOW))
    first = _run(service.issue("op-1"))
    second = _run(service.rotate(first))
    third = _run(service.rotate(second))
    assert first != second != third


def test_refresh_reuse_revokes_chain() -> None:
    service = RefreshRotationService(clock=lambda: float(_NOW))
    first = _run(service.issue("op-1"))
    second = _run(service.rotate(first))
    try:
        _run(service.rotate(first))
    except TokenError as exc:
        assert exc.reuse_detected is True
        assert exc.reason == "refresh_reuse"
    else:  # pragma: no cover
        raise AssertionError("la reutilización debía detectarse")
    try:
        _run(service.rotate(second))
    except TokenError as exc:
        assert exc.reason == "refresh_reuse"
    else:  # pragma: no cover
        raise AssertionError("la cadena debía quedar revocada")


def test_unknown_refresh_is_rejected() -> None:
    service = RefreshRotationService(clock=lambda: float(_NOW))
    try:
        _run(service.rotate("rt_desconocido"))
    except TokenError as exc:
        assert exc.reason == "refresh_unknown"
    else:  # pragma: no cover
        raise AssertionError("refresh desconocido debía rechazarse")


def test_refresh_revoke_reports_sub() -> None:
    service = RefreshRotationService(clock=lambda: float(_NOW))
    token = _run(service.issue("op-9"))
    assert _run(service.revoke(token)) == "op-9"
    assert _run(service.revoke("rt_inexistente")) is None


# =============================================================================
# Política de contraseñas
# =============================================================================
def test_password_policy_accepts_strong_password() -> None:
    validate_password_policy("ClaveSegura#2026", PasswordPolicy())


def test_password_policy_rejects_weak_passwords() -> None:
    policy = PasswordPolicy(min_length=12, require_complexity=True)
    for weak in ("corta#1", "sololetrasminusculas", "SinEspecial2026", "SinDigitos!!!!"):
        try:
            validate_password_policy(weak, policy)
        except PasswordPolicyError:
            continue
        else:  # pragma: no cover
            raise AssertionError(f"debió rechazarse: {weak}")


def test_password_policy_without_complexity_only_checks_length() -> None:
    validate_password_policy("sololetrasminusculas", PasswordPolicy(require_complexity=False))


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
