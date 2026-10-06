"""Verificación de la firma HMAC-SHA256 del webhook de Apps Script (spec §9.1–§9.3, T22).

Pivote definitivo: el origen (Google Sheets + Apps Script) autentica sus
notificaciones con **HMAC-SHA256** sobre una cadena canónica y un **secreto
compartido versionado** (``key_id``). La confidencialidad del tramo la aporta
TLS 1.3; el diseño anterior de sobre cifrado de aplicación y sus credenciales y
cabeceras de agente quedaron **retirados** (spec §9.1).

Cadena canónica y cabecera de firma (§9.2)::

    firma = HMAC-SHA256(secreto, canonical_string)
    canonical_string = "{webhook_id}|{key_id}|{nonce}|{timestamp}|{schema_version}|{sha256(cuerpo)}"
    X-Webhook-Signature: sha256=<hex>

Propiedades (fail-closed, §9.1, RF-01.e/f, AM-04/AM-05):

- **Comparación en tiempo constante** del digest (``hmac.compare_digest``).
- El **material del secreto** se resuelve por ``X-Webhook-Key-Id`` **vigente**
  desde el secret manager **en runtime**; **nunca** se lee de la BD ni se
  hardcodea. La BD (``webhook_registry``/``webhook_secret``) solo aporta
  **metadata** (``key_id``, estado y ventana ``not_before``/``not_after``,
  solape de rotación de 24 h, §9.3).
- Se validan las cabeceras y metadatos (``X-Webhook-Id``, ``X-Webhook-Key-Id``,
  ``X-Webhook-Nonce`` 128 bits, ``X-Webhook-Timestamp`` ISO-8601 UTC,
  ``X-Webhook-Version``) antes de tocar el cuerpo.
- El resultado es un objeto tipado (identidad verificada + ``key_id`` usado).

Fuera de alcance de T22 (tareas posteriores): anti-replay nonce/timestamp con
ventana ±300 s/caché 600 s (T24), cadena de verificación ordenada y orquestación
del endpoint ``POST /ingest/webhook`` (T23/T26). Aquí solo se expone la primitiva
de firma y la resolución del secreto.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import os
import re
import uuid
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Final, NoReturn, Protocol, runtime_checkable

from app.config import Settings, get_settings
from app.core.errors import raise_http_error
from app.core.logging import get_logger

logger = get_logger(__name__)

# --- Cabeceras del webhook (spec §2.2.1, §10.1) ------------------------------
WEBHOOK_ID_HEADER: Final = "X-Webhook-Id"
KEY_ID_HEADER: Final = "X-Webhook-Key-Id"
NONCE_HEADER: Final = "X-Webhook-Nonce"
TIMESTAMP_HEADER: Final = "X-Webhook-Timestamp"
VERSION_HEADER: Final = "X-Webhook-Version"
SIGNATURE_HEADER: Final = "X-Webhook-Signature"

# --- Formato de la firma (§9.2) ----------------------------------------------
SIGNATURE_ALGORITHM: Final = "sha256"
SIGNATURE_PREFIX: Final = f"{SIGNATURE_ALGORITHM}="
SIGNATURE_HEX_LEN: Final = 64  # SHA-256 = 32 bytes = 64 hex
NONCE_HEX_LEN: Final = 32  # 128 bits
SECRET_MIN_BYTES: Final = 32  # secreto de 256 bits (§9.2)
MAX_FIELD_LEN: Final = 128

_NONCE_RE: Final = re.compile(r"^[0-9a-fA-F]{32}$")
_SIGNATURE_RE: Final = re.compile(r"^[0-9a-fA-F]{64}$")
_HEX_RE: Final = re.compile(r"^[0-9a-fA-F]+$")
_TOKEN_RE: Final = re.compile(r"^[A-Za-z0-9._:@+-]+$")


class SecretMaterialError(Exception):
    """Material del secreto ausente o malformado en el secret manager."""


# =============================================================================
# Tipos de dominio
# =============================================================================
@dataclass(frozen=True)
class SignedWebhookHeaders:
    """Cabeceras de firma ya parseadas y validadas en formato."""

    webhook_id: str
    key_id: str
    nonce: str
    timestamp: datetime
    timestamp_raw: str
    version: str
    signature_hex: str


@dataclass(frozen=True)
class WebhookSecretMetadata:
    """Metadata de una versión del secreto (fila de ``app.webhook_secret``).

    **No contiene el material**: solo ``key_id``, ``webhook_id``, ``estado`` y la
    ventana de aceptación. El solape de rotación de 24 h (§9.3) se representa
    manteniendo **dos** versiones con ``estado="vigente"`` y ventanas solapadas;
    ``not_after`` acota la saliente.
    """

    key_id: str
    webhook_id: str
    estado: str = "vigente"
    not_before: datetime | None = None
    not_after: datetime | None = None

    def is_active(self, now: datetime) -> bool:
        """¿Es este ``key_id`` aceptable en ``now``? (estado vigente + ventana)."""
        if self.estado != "vigente":
            return False
        momento = _as_utc(now)
        if self.not_before is not None and momento < _as_utc(self.not_before):
            return False
        if self.not_after is not None and momento >= _as_utc(self.not_after):
            return False
        return True


@dataclass(frozen=True)
class VerifiedWebhook:
    """Resultado tipado: identidad del origen verificada + ``key_id`` usado."""

    webhook_id: str
    key_id: str
    nonce: str
    timestamp: datetime
    version: str
    schema_version: str
    content_sha256: str


# =============================================================================
# Secret manager (material inyectado en runtime, nunca de la BD)
# =============================================================================
@runtime_checkable
class SecretManager(Protocol):
    """Fuente del material del secreto de webhook (secret manager del entorno).

    Cualquier implementación (Vault, AWS/GCP Secret Manager, entorno) satisface
    el contrato devolviendo los bytes del secreto o ``None`` si no existe. El
    backend **nunca** lee el material de PostgreSQL (§9.2, RNF-02.e).
    """

    def get_webhook_secret(self, *, webhook_id: str, key_id: str) -> bytes | None:
        """Devuelve el material del secreto para ``(webhook_id, key_id)`` o ``None``."""
        ...


def decode_secret_material(material: str, *, name: str = "secreto de webhook") -> bytes:
    """Decodifica material de secreto hex o base64 (incluido base64url) a bytes.

    Se exige un mínimo de 256 bits (32 bytes) para el secreto compartido (§9.2).
    """
    value = material.strip()
    if not value:
        raise SecretMaterialError(f"Material de {name} ausente en el secret manager (RNF-13).")
    candidates: list[bytes] = []
    if _HEX_RE.match(value) and len(value) % 2 == 0:
        try:
            candidates.append(bytes.fromhex(value))
        except ValueError:
            pass
    for altchars in (None, b"-_"):
        try:
            candidates.append(base64.b64decode(value, altchars=altchars, validate=True))
        except (binascii.Error, ValueError):
            pass
    for raw in candidates:
        if len(raw) >= SECRET_MIN_BYTES:
            return raw
    raise SecretMaterialError(f"Material de {name} inválido: se esperan ≥ 256 bits (hex o base64).")


class EnvironmentSecretManager:
    """Secret manager respaldado por variables inyectadas en runtime.

    Orden de resolución del material (nunca desde la BD):

    1. ``WEBHOOK_SECRETS``: JSON ``{"<webhook_id>:<key_id>": "<hex|base64>", ...}``
       o ``{"<key_id>": "<hex|base64>"}``, inyectado por el secret manager. Es la
       forma que soporta el **solape de rotación** (dos ``key_id`` a la vez).
    2. Fallback de un único secreto (desarrollo): ``WEBHOOK_SECRET`` (o
       ``Settings.webhook_secret``) cuando ``key_id`` coincide con
       ``WEBHOOK_KEY_ID`` (y ``WEBHOOK_ID`` si está definido).
    """

    def __init__(
        self,
        settings: Settings | None = None,
        environ: Mapping[str, str] | None = None,
    ) -> None:
        self._settings = settings or get_settings()
        self._environ: Mapping[str, str] = os.environ if environ is None else environ

    def get_webhook_secret(self, *, webhook_id: str, key_id: str) -> bytes | None:
        raw_map = (self._environ.get("WEBHOOK_SECRETS") or "").strip()
        if raw_map:
            mapping: object = None
            try:
                mapping = json.loads(raw_map)
            except ValueError:
                logger.warning(
                    "webhook_secrets_malformed",
                    extra={"event": "secret_manager", "result": "rejected"},
                )
            if isinstance(mapping, dict):
                for candidate_key in (f"{webhook_id}:{key_id}", key_id):
                    material = mapping.get(candidate_key)
                    if isinstance(material, str) and material.strip():
                        return decode_secret_material(material)

        single_key_id = self._settings.webhook_key_id or ""
        single_webhook_id = self._settings.webhook_id or ""
        if key_id == single_key_id and (not single_webhook_id or webhook_id == single_webhook_id):
            material = (self._environ.get("WEBHOOK_SECRET") or "").strip()
            if not material:
                material = self._settings.webhook_secret
            if material:
                return decode_secret_material(material)
        return None


# =============================================================================
# Utilidades internas
# =============================================================================
def _as_utc(value: datetime) -> datetime:
    """Normaliza a UTC (asume UTC si el ``datetime`` viene sin zona)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _get_header(headers: Mapping[str, str], name: str) -> str:
    """Lee una cabecera de forma insensible a mayúsculas (dict plano o Starlette)."""
    value = headers.get(name)
    if value is None:
        lowered = name.lower()
        for key in headers:
            if key.lower() == lowered:
                value = headers[key]
                break
    return str(value).strip() if value is not None else ""


def _reject(message: str) -> NoReturn:
    raise_http_error("UNAUTHORIZED", message)


def _validate_field(value: str, *, message: str) -> str:
    """Valida un campo que entra en la cadena canónica (sin ``|`` ni control)."""
    if not value or len(value) > MAX_FIELD_LEN:
        _reject(message)
    if "|" in value or not value.isprintable() or not _TOKEN_RE.match(value):
        _reject(message)
    return value


def _normalize_identifier(value: str) -> str:
    """Normaliza un identificador para comparación (UUID canónico o minúsculas)."""
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError, TypeError):
        return value.strip().lower()


# =============================================================================
# Cadena canónica + firma
# =============================================================================
def parse_signed_headers(headers: Mapping[str, str]) -> SignedWebhookHeaders:
    """Valida presencia y formato de las cabeceras de firma (§2.2.1 paso 1).

    Rechaza con ``401`` cualquier cabecera ausente o malformada. No consume ni
    interpreta el cuerpo.
    """
    webhook_id = _validate_field(
        _get_header(headers, WEBHOOK_ID_HEADER),
        message=f"{WEBHOOK_ID_HEADER} ausente o malformado.",
    )
    key_id = _validate_field(
        _get_header(headers, KEY_ID_HEADER),
        message=f"{KEY_ID_HEADER} ausente o malformado.",
    )
    nonce = _get_header(headers, NONCE_HEADER)
    if len(nonce) != NONCE_HEX_LEN or not _NONCE_RE.match(nonce):
        _reject(f"{NONCE_HEADER} ausente o malformado (128 bits hex esperados).")
    nonce = nonce.lower()

    timestamp_raw = _get_header(headers, TIMESTAMP_HEADER)
    timestamp = parse_iso8601_utc(timestamp_raw)

    version = _validate_field(
        _get_header(headers, VERSION_HEADER),
        message=f"{VERSION_HEADER} ausente o malformado.",
    )

    signature_header = _get_header(headers, SIGNATURE_HEADER)
    if not signature_header.startswith(SIGNATURE_PREFIX):
        _reject(f"{SIGNATURE_HEADER} ausente o con algoritmo no soportado (se espera sha256=).")
    signature_hex = signature_header[len(SIGNATURE_PREFIX) :].strip()
    if len(signature_hex) != SIGNATURE_HEX_LEN or not _SIGNATURE_RE.match(signature_hex):
        _reject(f"{SIGNATURE_HEADER} malformada (hex de 256 bits esperado).")

    return SignedWebhookHeaders(
        webhook_id=webhook_id,
        key_id=key_id,
        nonce=nonce,
        timestamp=timestamp,
        timestamp_raw=timestamp_raw,
        version=version,
        signature_hex=signature_hex.lower(),
    )


def parse_iso8601_utc(value: str) -> datetime:
    """Parsea ``X-Webhook-Timestamp`` (ISO-8601 con zona; ``Z`` = UTC)."""
    if not value or len(value) > 64:
        _reject(f"{TIMESTAMP_HEADER} ausente o malformado.")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _reject(f"{TIMESTAMP_HEADER} no es ISO-8601 válido.")
    if parsed.tzinfo is None:
        _reject(f"{TIMESTAMP_HEADER} sin zona horaria (se exige UTC).")
    return parsed.astimezone(timezone.utc)


def compute_content_sha256(body: bytes) -> str:
    """``sha256(cuerpo)`` en hex minúsculas (último campo de la cadena canónica)."""
    return hashlib.sha256(body).hexdigest()


def build_canonical_string(
    *,
    webhook_id: str,
    key_id: str,
    nonce: str,
    timestamp: str,
    schema_version: str,
    content_sha256: str,
) -> str:
    """Construye la cadena canónica **exacta** de §9.2.

    ``timestamp`` es la cadena **cruda** de ``X-Webhook-Timestamp`` (lo que firmó
    el origen), no su reformateo; así la firma es interoperable con Apps Script.
    """
    return f"{webhook_id}|{key_id}|{nonce}|{timestamp}|{schema_version}|{content_sha256}"


def compute_signature_hex(secret: bytes, canonical_string: str) -> str:
    """HMAC-SHA256(secreto, cadena canónica) en hex minúsculas."""
    return hmac.new(secret, canonical_string.encode("utf-8"), hashlib.sha256).hexdigest()


def signatures_match(secret: bytes, canonical_string: str, provided_hex: str) -> bool:
    """Compara la firma provista con la esperada en **tiempo constante**."""
    expected = compute_signature_hex(secret, canonical_string)
    provided = provided_hex.strip().lower().encode("ascii")
    return hmac.compare_digest(expected.encode("ascii"), provided)


# =============================================================================
# Resolución de la versión vigente + verificación
# =============================================================================
def find_active_secret_metadata(
    candidates: Iterable[WebhookSecretMetadata],
    *,
    key_id: str,
    now: datetime | None = None,
) -> WebhookSecretMetadata:
    """Elige la metadata del ``key_id`` **vigente** en ``now`` (soporta solape).

    Durante la ventana de rotación pueden existir dos ``key_id`` activos; se
    selecciona el que coincide con la cabecera y está dentro de su ventana. Si
    ninguno está vigente ⇒ ``403 KEY_NOT_ACTIVE`` (fail-closed, §9.3).
    """
    momento = _as_utc(now) if now is not None else _now_utc()
    for meta in candidates:
        if meta.key_id == key_id and meta.is_active(momento):
            return meta
    raise_http_error("KEY_NOT_ACTIVE", "key_id no vigente o fuera de la ventana de rotación.")


def resolve_webhook_secret(
    metadata: WebhookSecretMetadata,
    secret_manager: SecretManager,
    *,
    now: datetime | None = None,
) -> bytes:
    """Resuelve el material del secreto desde el secret manager (nunca la BD).

    Requiere ``metadata`` vigente y que el secret manager entregue el material
    para ``(webhook_id, key_id)``; en caso contrario falla cerrado.
    """
    momento = _as_utc(now) if now is not None else _now_utc()
    if not metadata.is_active(momento):
        raise_http_error("KEY_NOT_ACTIVE", "key_id no vigente o fuera de la ventana de rotación.")
    secret = secret_manager.get_webhook_secret(
        webhook_id=metadata.webhook_id, key_id=metadata.key_id
    )
    if secret is None:
        raise_http_error("UNAVAILABLE", "Secreto del webhook no disponible en el secret manager.")
    return secret


def verify_webhook_signature(
    *,
    body: bytes,
    headers: Mapping[str, str],
    metadata_candidates: Iterable[WebhookSecretMetadata],
    secret_manager: SecretManager,
    now: datetime | None = None,
    schema_version: str | None = None,
) -> VerifiedWebhook:
    """Verifica la firma HMAC-SHA256 de un webhook (primitiva de T22).

    Orden fail-closed:

    1. Formato/presencia de cabeceras de firma (``401`` si falla).
    2. ``key_id`` vigente entre las versiones conocidas (``403`` si no).
    3. Resolución del material desde el secret manager (``503`` si falta).
    4. Recomputo de la cadena canónica §9.2 y comparación en tiempo constante
       (``401`` si no coincide). El cuerpo **no** se deserializa.

    ``schema_version`` entra en la cadena canónica; por defecto se toma de
    ``X-Webhook-Version`` (única versión disponible antes de tocar el cuerpo).
    """
    parsed = parse_signed_headers(headers)

    metadata = find_active_secret_metadata(metadata_candidates, key_id=parsed.key_id, now=now)

    # Binding: la cabecera y la metadata deben referirse al mismo origen
    # (comparación constante, AM-04).
    if not hmac.compare_digest(
        _normalize_identifier(parsed.webhook_id).encode("utf-8"),
        _normalize_identifier(metadata.webhook_id).encode("utf-8"),
    ):
        _reject("X-Webhook-Id no corresponde al origen registrado.")

    secret = resolve_webhook_secret(metadata, secret_manager, now=now)

    canonical_version = schema_version or parsed.version
    content_sha256 = compute_content_sha256(body)
    canonical = build_canonical_string(
        webhook_id=parsed.webhook_id,
        key_id=parsed.key_id,
        nonce=parsed.nonce,
        timestamp=parsed.timestamp_raw,
        schema_version=canonical_version,
        content_sha256=content_sha256,
    )
    if not signatures_match(secret, canonical, parsed.signature_hex):
        _reject("Firma HMAC-SHA256 inválida.")

    return VerifiedWebhook(
        webhook_id=metadata.webhook_id,
        key_id=metadata.key_id,
        nonce=parsed.nonce,
        timestamp=parsed.timestamp,
        version=parsed.version,
        schema_version=canonical_version,
        content_sha256=content_sha256,
    )
