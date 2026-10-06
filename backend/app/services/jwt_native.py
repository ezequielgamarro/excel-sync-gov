"""Auth nativa JWT (spec §2.2.2, RNF-03.a/b, T35).

El backend **emite y verifica sus propios JWT** (no hay IdP externo):

- **Access token** de vida corta (15 min) firmado con ``JWT_SIGNING_KEY``
  (``HS256``; también se admite ``RS256`` con clave privada PEM). Claims
  obligatorios: ``iss``, ``aud`` (``dashboard-api``), ``sub``, ``jti``, ``iat``,
  ``nbf``, ``exp`` y las ``roles``/``capabilities`` del operador.
- **Refresh token rotativo** con **detección de reutilización**: reutilizar un
  refresh ya rotado/revocado **revoca la cadena completa** (reuse detection).

Secretos: la clave de firma se inyecta desde el entorno/secret manager; nunca se
hardcodea ni se registra (RNF-13). Los mensajes de error son genéricos
(fail-closed) y no filtran detalle al cliente.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
import time as _time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

DEFAULT_ACCESS_TOKEN_TTL_SECONDS = 900
DEFAULT_CLOCK_SKEW_SECONDS = 60
SUPPORTED_ALGORITHMS: frozenset[str] = frozenset({"HS256", "RS256"})


class TokenError(Exception):
    """Token inválido (autenticación fallida). Mensaje genérico, sin detalle."""

    def __init__(self, reason: str, *, reuse_detected: bool = False) -> None:
        super().__init__(reason)
        self.reason = reason
        self.reuse_detected = reuse_detected


@dataclass(frozen=True)
class NativeJwtConfig:
    """Configuración de la emisión/validación de JWT propios."""

    issuer: str
    audience: str
    signing_key: str = ""
    algorithm: str = "HS256"
    access_token_ttl_seconds: int = DEFAULT_ACCESS_TOKEN_TTL_SECONDS
    clock_skew_seconds: int = DEFAULT_CLOCK_SKEW_SECONDS


@dataclass(frozen=True)
class AccessTokenClaims:
    """Claims verificados de un access token (sub + roles + capacidades)."""

    sub: str
    roles: frozenset[str]
    capabilities: frozenset[str]
    jti: str
    issued_at: int
    not_before: int
    expires_at: int
    raw: dict[str, Any] = field(default_factory=dict)


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(segment: str) -> bytes:
    padding = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + padding)


def decode_segments(token: str) -> tuple[dict[str, Any], dict[str, Any], bytes, bytes]:
    """Separa y decodifica un JWT (header, payload, signing_input, signature)."""
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
    except ValueError as exc:
        raise TokenError("malformed") from exc
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    try:
        header = json.loads(_b64url_decode(header_b64))
        payload = json.loads(_b64url_decode(payload_b64))
        signature = _b64url_decode(signature_b64)
    except (ValueError, binascii.Error, UnicodeDecodeError) as exc:
        raise TokenError("malformed") from exc
    if not isinstance(header, dict) or not isinstance(payload, dict):
        raise TokenError("malformed")
    return header, payload, signing_input, signature


class NativeJwtService:
    """Emite y valida access tokens JWT firmados por el backend."""

    def __init__(
        self,
        config: NativeJwtConfig,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._config = config
        self._clock = clock or _time.time

    @property
    def config(self) -> NativeJwtConfig:
        return self._config

    # --- Emisión -------------------------------------------------------------
    def issue_access_token(
        self,
        *,
        sub: str,
        roles: list[str] | set[str] | frozenset[str] = (),
        capabilities: list[str] | set[str] | frozenset[str] = (),
        jti: str | None = None,
        now: int | None = None,
    ) -> str:
        """Firma un access token de vida corta con ``sub``, roles y capacidades."""
        if not self._config.signing_key:
            raise TokenError("signing_key_missing")
        issued_at = int(now if now is not None else self._clock())
        ttl = self._config.access_token_ttl_seconds
        header = {"alg": self._config.algorithm, "typ": "JWT"}
        payload: dict[str, Any] = {
            "iss": self._config.issuer,
            "aud": self._config.audience,
            "sub": sub,
            "jti": jti or secrets.token_urlsafe(16),
            "iat": issued_at,
            "nbf": issued_at,
            "exp": issued_at + ttl,
            "roles": sorted({str(role) for role in roles}),
            "capabilities": sorted({str(cap) for cap in capabilities}),
        }
        return self._sign(header, payload)

    def _sign(self, header: dict[str, Any], payload: dict[str, Any]) -> str:
        head = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
        body = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        signing_input = f"{head}.{body}".encode("ascii")
        signature = self._sign_bytes(signing_input)
        return f"{head}.{body}.{_b64url_encode(signature)}"

    def _sign_bytes(self, signing_input: bytes) -> bytes:
        alg = self._config.algorithm
        if alg == "HS256":
            return hmac.new(
                self._config.signing_key.encode("utf-8"), signing_input, hashlib.sha256
            ).digest()
        if alg == "RS256":
            return _rs256_sign(self._config.signing_key, signing_input)
        raise TokenError("alg_not_allowed")

    # --- Validación ----------------------------------------------------------
    def validate_access_token(self, token: str) -> AccessTokenClaims:
        """Valida firma y claims; lanza ``TokenError`` si algo no cuadra."""
        header, payload, signing_input, signature = decode_segments(token)

        alg = str(header.get("alg") or "")
        if alg not in SUPPORTED_ALGORITHMS or alg != self._config.algorithm:
            raise TokenError("alg_not_allowed")
        if not self._config.signing_key:
            raise TokenError("signing_key_missing")

        if alg == "HS256":
            expected = hmac.new(
                self._config.signing_key.encode("utf-8"), signing_input, hashlib.sha256
            ).digest()
            valid = hmac.compare_digest(expected, signature)
        else:  # RS256
            valid = _rs256_verify(self._config.signing_key, signing_input, signature)
        if not valid:
            raise TokenError("bad_signature")

        self._validate_claims(payload)
        return self._to_claims(payload)

    def _validate_claims(self, payload: dict[str, Any]) -> None:
        now = int(self._clock())
        leeway = self._config.clock_skew_seconds

        if str(payload.get("iss") or "") != self._config.issuer:
            raise TokenError("bad_issuer")

        audiences = payload.get("aud")
        if isinstance(audiences, str):
            audiences = [audiences]
        if not isinstance(audiences, list) or self._config.audience not in audiences:
            raise TokenError("bad_audience")

        exp = payload.get("exp")
        nbf = payload.get("nbf")
        iat = payload.get("iat")
        if not isinstance(exp, (int, float)) or not isinstance(iat, (int, float)):
            raise TokenError("missing_temporal_claims")
        if now > int(exp) + leeway:
            raise TokenError("expired")
        if not isinstance(nbf, (int, float)) or now + leeway < int(nbf):
            raise TokenError("not_yet_valid")
        if int(iat) - leeway > now:
            raise TokenError("issued_in_future")
        if int(exp) - int(iat) > self._config.access_token_ttl_seconds + leeway:
            raise TokenError("token_lifetime_too_long")
        if not payload.get("jti"):
            raise TokenError("missing_jti")

    def _to_claims(self, payload: dict[str, Any]) -> AccessTokenClaims:
        sub = str(payload.get("sub") or "")
        if not sub:
            raise TokenError("missing_sub")

        raw_roles = payload.get("roles")
        roles = {str(role) for role in raw_roles if role} if isinstance(raw_roles, list) else set()

        raw_caps = payload.get("capabilities")
        if isinstance(raw_caps, list):
            capabilities = {str(cap) for cap in raw_caps if cap}
        elif isinstance(raw_caps, str):
            capabilities = {cap.strip() for cap in raw_caps.split(",") if cap.strip()}
        else:
            capabilities = set()

        return AccessTokenClaims(
            sub=sub,
            roles=frozenset(roles),
            capabilities=frozenset(capabilities),
            jti=str(payload.get("jti") or ""),
            issued_at=int(payload.get("iat") or 0),
            not_before=int(payload.get("nbf") or 0),
            expires_at=int(payload.get("exp") or 0),
            raw=payload,
        )


# RS256 (opcional): la clave privada PEM se inyecta desde el secret manager. La
# dependencia ``cryptography`` se importa de forma perezosa.
def _rs256_sign(private_key_pem: str, signing_input: bytes) -> bytes:  # pragma: no cover
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import padding

    key = serialization.load_pem_private_key(private_key_pem.encode("utf-8"), password=None)
    return key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())


def _rs256_verify(  # pragma: no cover
    private_key_pem: str, signing_input: bytes, signature: bytes
) -> bool:
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        key = serialization.load_pem_private_key(
            private_key_pem.encode("utf-8"), password=None
        )
        key.public_key().verify(
            signature, signing_input, padding.PKCS1v15(), hashes.SHA256()
        )
        return True
    except Exception:
        return False


# =============================================================================
# Refresh token rotativo con detección de reutilización (RNF-03.b)
# =============================================================================
ACTIVE = "active"
ROTATED = "rotated"
REVOKED = "revoked"


@dataclass
class RefreshRecord:
    token_id: str
    chain_id: str
    sub: str
    status: str
    issued_at: int
    rotated_at: int | None = None


class RefreshStore(Protocol):
    """Almacén de registros de refresh (Redis, memoria o PostgreSQL)."""

    async def get(self, token_id: str) -> RefreshRecord | None: ...

    async def put(self, record: RefreshRecord) -> None: ...

    async def revoke_chain(self, chain_id: str) -> None: ...


class InMemoryRefreshStore:
    """Almacén en memoria (desarrollo/pruebas; no distribuido)."""

    def __init__(self) -> None:
        self.records: dict[str, RefreshRecord] = {}

    async def get(self, token_id: str) -> RefreshRecord | None:
        return self.records.get(token_id)

    async def put(self, record: RefreshRecord) -> None:
        self.records[record.token_id] = record

    async def revoke_chain(self, chain_id: str) -> None:
        for record in self.records.values():
            if record.chain_id == chain_id:
                record.status = REVOKED


class RefreshRotationService:
    """Emite y rota refresh tokens con detección de reutilización.

    La cadena es **indefinida mientras hay actividad** (sin TTL fijo): el cliente
    renueva con el latido del WSS/heartbeat. Reutilizar un token ya rotado/revocado
    revoca la cadena completa y lanza ``TokenError(reuse_detected=True)``.
    """

    def __init__(
        self,
        store: RefreshStore | None = None,
        *,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._store = store or InMemoryRefreshStore()
        self._clock = clock or _time.time

    @staticmethod
    def _new_id(prefix: str) -> str:
        return f"{prefix}_{secrets.token_urlsafe(32)}"

    async def issue(self, sub: str) -> str:
        """Inicia una cadena nueva para ``sub`` y devuelve el refresh token."""
        chain_id = self._new_id("rtc")
        token_id = self._new_id("rt")
        await self._store.put(
            RefreshRecord(
                token_id=token_id,
                chain_id=chain_id,
                sub=sub,
                status=ACTIVE,
                issued_at=int(self._clock()),
            )
        )
        return token_id

    async def rotate(self, refresh_token: str) -> str:
        """Rota un refresh token activo y devuelve el siguiente."""
        record = await self._store.get(refresh_token)
        if record is None:
            raise TokenError("refresh_unknown")
        if record.status in (ROTATED, REVOKED):
            await self._store.revoke_chain(record.chain_id)
            raise TokenError("refresh_reuse", reuse_detected=True)
        if record.status != ACTIVE:
            raise TokenError("refresh_invalid")

        record.status = ROTATED
        record.rotated_at = int(self._clock())
        await self._store.put(record)

        next_token = self._new_id("rt")
        await self._store.put(
            RefreshRecord(
                token_id=next_token,
                chain_id=record.chain_id,
                sub=record.sub,
                status=ACTIVE,
                issued_at=int(self._clock()),
            )
        )
        return next_token

    async def lookup(self, refresh_token: str) -> RefreshRecord | None:
        """Devuelve el registro sin rotarlo (para logout/inspección)."""
        return await self._store.get(refresh_token)

    async def revoke(self, refresh_token: str) -> str | None:
        """Revoca la cadena del refresh indicado; devuelve el ``sub`` si existe."""
        record = await self._store.get(refresh_token)
        if record is None:
            return None
        await self._store.revoke_chain(record.chain_id)
        return record.sub
