"""Provisión y rotación del secreto del webhook (spec §9.2–§9.4, §10.1, T27).

Este módulo **migra** el flujo antiguo de activación de agentes (retirado en el
pivote a Google Sheets + Apps Script) al único flujo vigente: la **gestión del
secreto de firma del webhook** que el ``platform-admin`` provisiona/rota.

Contrato (spec §9.2–§9.4, §10.1):

- La propuesta genera un ``webhook_id`` (UUIDv7) en el **alta nueva** y un
  ``key_id`` versionado; el **material del secreto** es aleatorio de alta
  entropía (256 bits, §9.2) y se entrega **una sola vez** (jamás se relee de la
  API ni se persiste en la BD).
- En la BD solo se guarda **metadata** (``app.webhook_registry`` y
  ``app.webhook_secret``): estado, ``not_before``/``not_after`` y ``rotated_at``.
  El material va al **secret manager** (``WebhookSecretStore``; en Apps Script se
  custodia en ``Script Properties``), nunca a la base de datos (§9.5, RNF-02.e).
- La **rotación** mantiene vigentes el secreto anterior y el nuevo durante un
  **solape de 24 h** (§9.3): la versión saliente recibe ``not_after`` dentro de
  la ventana y la nueva arranca en ``not_before``.
- Se emite **auditoría** ``platform.webhook.secret_rotated`` con el ``actor``
  (``sub`` del operador) y el ``correlation_id`` de la petición (RNF-08).
"""

from __future__ import annotations

import json
import os
import re
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import func, insert, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.errors import raise_http_error
from app.core.logging import get_logger
from app.models.tables import webhook_registry, webhook_secret
from app.services.audit import record_audit

logger = get_logger(__name__)

#: Solape de rotación entre la versión saliente y la entrante (§9.3).
OVERLAP_HOURS: int = 24

#: Tamaño del secreto compartido: 256 bits (§9.2).
SECRET_BYTES: int = 32

#: Acción de auditoría de la rotación/provisión del secreto (§10.1, RNF-08).
WEBHOOK_SECRET_ROTATED_ACTION: str = "platform.webhook.secret_rotated"

_KEY_ID_RE = re.compile(r"^[A-Za-z0-9._:-]{3,64}$")


@dataclass(frozen=True)
class WebhookSecretRotation:
    """Resultado de una provisión/rotación (el ``secret`` se muestra una sola vez)."""

    webhook_id: str
    key_id: str
    secret: str
    doc_id: str
    room_id: str
    created: bool
    overlap_until: datetime | None


@runtime_checkable
class WebhookSecretStore(Protocol):
    """Custodia del **material** del secreto (secret manager; nunca la BD).

    La implementación de producción inyecta el material en el secret manager del
    entorno (Vault, AWS/GCP Secret Manager…). El backend solo guarda metadata en
    ``app.webhook_secret`` (§9.2, RNF-02.e).
    """

    def put_webhook_secret(self, *, webhook_id: str, key_id: str, material: bytes) -> None:
        """Guarda el material del secreto para ``(webhook_id, key_id)``."""
        ...


class EnvironmentWebhookSecretStore:
    """Adaptador de secret manager respaldado por el entorno de ejecución.

    Fusiona ``{webhook_id}:{key_id} -> <hex>`` en ``WEBHOOK_SECRETS`` para que el
    verificador (``EnvironmentSecretManager``) resuelva el secreto vigente en
    runtime. Es el adaptador de desarrollo/pruebas: **no** escribe en la BD, no
    registra el material y conserva las versiones antiguas durante el solape. La
    implementación de producción se inyecta con el mismo contrato.
    """

    def put_webhook_secret(self, *, webhook_id: str, key_id: str, material: bytes) -> None:
        mapping: dict[str, str] = {}
        raw = (os.environ.get("WEBHOOK_SECRETS") or "").strip()
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    mapping = {str(k): str(v) for k, v in parsed.items()}
            except ValueError:
                mapping = {}
        mapping[f"{webhook_id}:{key_id}"] = material.hex()
        os.environ["WEBHOOK_SECRETS"] = json.dumps(mapping)


_default_secret_store: EnvironmentWebhookSecretStore | None = None


def get_default_secret_store() -> EnvironmentWebhookSecretStore:
    """Devuelve el adaptador por defecto (singleton) del secret manager."""
    global _default_secret_store
    if _default_secret_store is None:
        _default_secret_store = EnvironmentWebhookSecretStore()
    return _default_secret_store


def _as_utc(value: datetime) -> datetime:
    """Normaliza a UTC (asume UTC si viene sin zona)."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def generate_webhook_id() -> uuid.UUID:
    """Genera un ``webhook_id`` UUIDv7 (RFC 9562) para el alta nueva.

    Mismo formato que ``app.uuidv7()`` de la migración ``0001_base``: 48 bits de
    timestamp Unix en milisegundos (big-endian), nibble de versión 7 y variante
    10xx; el resto aleatorio.
    """
    ts_ms = int(time.time() * 1000) & ((1 << 48) - 1)
    rand = os.urandom(10)
    buf = bytearray(16)
    buf[0:6] = ts_ms.to_bytes(6, "big")
    buf[6] = (rand[0] & 0x0F) | 0x70  # versión 7
    buf[7] = rand[1]
    buf[8] = (rand[2] & 0x3F) | 0x80  # variante 10xx
    buf[9:16] = rand[3:10]
    return uuid.UUID(bytes=bytes(buf))


def generate_key_id(now: datetime) -> str:
    """Genera un ``key_id`` versionado único (p. ej. ``wk-202610-3f9a1c02``)."""
    return f"wk-{now:%Y%m}-{secrets.token_hex(4)}"


def generate_secret_material() -> bytes:
    """Genera el material del secreto: 256 bits de alta entropía (§9.2)."""
    return secrets.token_bytes(SECRET_BYTES)


def _parse_webhook_uuid(webhook_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(webhook_id)
    except (ValueError, AttributeError, TypeError):
        raise_http_error("BAD_REQUEST", "webhook_id no es un UUID válido.")


# =============================================================================
# Persistencia de metadata (aislada para permitir pruebas con dobles)
# =============================================================================
async def _fetch_registry(session: AsyncSession, webhook_uuid: uuid.UUID) -> Any | None:
    return (
        await session.execute(
            select(
                webhook_registry.c.estado,
                webhook_registry.c.revoked_at,
                webhook_registry.c.doc_id,
                webhook_registry.c.room_id,
            ).where(webhook_registry.c.webhook_id == webhook_uuid)
        )
    ).first()


async def _fetch_active_key_ids(
    session: AsyncSession, webhook_uuid: uuid.UUID, momento: datetime
) -> list[str]:
    rows = (
        await session.execute(
            select(webhook_secret.c.key_id).where(
                webhook_secret.c.webhook_id == webhook_uuid,
                webhook_secret.c.estado == "vigente",
                or_(
                    webhook_secret.c.not_after.is_(None),
                    webhook_secret.c.not_after > momento,
                ),
            )
        )
    ).all()
    return [str(row[0]) for row in rows]


async def _key_id_exists(session: AsyncSession, key_id: str) -> bool:
    return (
        await session.execute(
            select(webhook_secret.c.key_id).where(webhook_secret.c.key_id == key_id).limit(1)
        )
    ).first() is not None


async def _find_active_by_doc(session: AsyncSession, doc_id: str) -> uuid.UUID | None:
    """Devuelve el ``webhook_id`` activo de un documento (uno por documento, §9.4)."""
    row = (
        await session.execute(
            select(webhook_registry.c.webhook_id)
            .where(
                webhook_registry.c.doc_id == doc_id,
                webhook_registry.c.estado == "activo",
                webhook_registry.c.revoked_at.is_(None),
            )
            .limit(1)
        )
    ).first()
    return row[0] if row is not None else None


async def _insert_registry(
    session: AsyncSession,
    *,
    webhook_uuid: uuid.UUID,
    doc_id: str,
    room_id: str,
    momento: datetime,
) -> None:
    await session.execute(
        insert(webhook_registry).values(
            webhook_id=webhook_uuid,
            doc_id=doc_id,
            room_id=room_id,
            estado="activo",
            created_at=momento,
        )
    )


async def _insert_secret(
    session: AsyncSession,
    *,
    key_id: str,
    webhook_uuid: uuid.UUID,
    momento: datetime,
) -> None:
    await session.execute(
        insert(webhook_secret).values(
            key_id=key_id,
            webhook_id=webhook_uuid,
            estado="vigente",
            not_before=momento,
            not_after=None,
            created_at=momento,
            rotated_at=None,
        )
    )


async def _retire_previous_keys(
    session: AsyncSession,
    *,
    webhook_uuid: uuid.UUID,
    new_key_id: str,
    overlap_until: datetime,
    momento: datetime,
) -> None:
    """Acota la ventana de las versiones anteriores al solape de 24 h (§9.3).

    No alarga ventanas ya cerradas: ``not_after`` se fija al **mínimo** entre la
    ventana previa (si existe) y ``overlap_until``.
    """
    bounded_not_after = func.least(
        func.coalesce(webhook_secret.c.not_after, overlap_until), overlap_until
    )
    await session.execute(
        update(webhook_secret)
        .where(
            webhook_secret.c.webhook_id == webhook_uuid,
            webhook_secret.c.key_id != new_key_id,
            webhook_secret.c.estado == "vigente",
            or_(
                webhook_secret.c.not_after.is_(None),
                webhook_secret.c.not_after > overlap_until,
            ),
        )
        .values(not_after=bounded_not_after, rotated_at=momento)
    )


# =============================================================================
# Provisión / rotación
# =============================================================================
async def rotate_webhook_secret(
    session: AsyncSession,
    *,
    actor: str,
    correlation_id: str = "",
    webhook_id: str | None = None,
    doc_id: str | None = None,
    room_id: str | None = None,
    key_id: str | None = None,
    secret_store: WebhookSecretStore | None = None,
    now: datetime | None = None,
) -> WebhookSecretRotation:
    """Provisiona (alta nueva) o rota el secreto del webhook.

    - ``webhook_id`` ausente ⇒ **alta nueva** (UUIDv7); requiere ``doc_id``.
    - ``webhook_id`` presente ⇒ **rotación** de un origen existente y activo.
    - Genera ``key_id`` y material de 256 bits; el material se entrega **una sola
      vez** y se deposita en el secret manager (nunca en la BD).
    - Durante **24 h** el ``key_id`` anterior y el nuevo son aceptados (§9.3).
    - Emite auditoría ``platform.webhook.secret_rotated`` en la sesión de negocio.
    """
    settings = get_settings()
    store: WebhookSecretStore = secret_store or get_default_secret_store()
    momento = _as_utc(now) if now is not None else datetime.now(timezone.utc)

    # 1. Resolver el origen (alta nueva vs. rotación) y su metadata de registro.
    if webhook_id:
        webhook_uuid = _parse_webhook_uuid(webhook_id)
        row = await _fetch_registry(session, webhook_uuid)
        if row is None:
            raise_http_error("NOT_FOUND", "El webhook no está registrado.")
        if row.estado != "activo" or row.revoked_at is not None:
            raise_http_error("FORBIDDEN", "El webhook está revocado o inactivo.")
        resolved_doc_id = doc_id or str(row.doc_id)
        if doc_id and str(row.doc_id) != doc_id:
            raise_http_error("CONFLICT", "doc_id no corresponde al webhook registrado.")
        resolved_room_id = room_id or str(row.room_id or settings.default_room_id)
        created = False
    else:
        if not doc_id:
            raise_http_error("UNPROCESSABLE", "doc_id es obligatorio para el alta del webhook.")
        existing_webhook = await _find_active_by_doc(session, doc_id)
        if existing_webhook is not None:
            raise_http_error(
                "CONFLICT",
                "Ya existe un webhook activo para el documento; use la rotación.",
                status_code=409,
            )
        webhook_uuid = generate_webhook_id()
        resolved_doc_id = doc_id
        resolved_room_id = room_id or settings.default_room_id
        await _insert_registry(
            session,
            webhook_uuid=webhook_uuid,
            doc_id=resolved_doc_id,
            room_id=resolved_room_id,
            momento=momento,
        )
        created = True

    # 2. ``key_id`` versionado (único) para la nueva versión del secreto.
    resolved_key_id = key_id.strip() if key_id else generate_key_id(momento)
    if not _KEY_ID_RE.match(resolved_key_id):
        raise_http_error("BAD_REQUEST", "key_id con formato inválido.")
    if await _key_id_exists(session, resolved_key_id):
        raise_http_error("CONFLICT", "key_id ya existe.", status_code=409)

    # 3. Solape de 24 h: la(s) versión(es) vigente(s) pasan a cerrar su ventana.
    previous = await _fetch_active_key_ids(session, webhook_uuid, momento)
    overlap_until = momento + timedelta(hours=OVERLAP_HOURS) if previous else None
    if overlap_until is not None:
        await _retire_previous_keys(
            session,
            webhook_uuid=webhook_uuid,
            new_key_id=resolved_key_id,
            overlap_until=overlap_until,
            momento=momento,
        )

    # 4. Metadata de la nueva versión (solo metadata; sin material).
    await _insert_secret(
        session,
        key_id=resolved_key_id,
        webhook_uuid=webhook_uuid,
        momento=momento,
    )

    # 5. Material al secret manager (entregado una sola vez; jamás a la BD).
    material = generate_secret_material()
    store.put_webhook_secret(
        webhook_id=str(webhook_uuid), key_id=resolved_key_id, material=material
    )

    # 6. Auditoría de la rotación/provisión (actor = sub; correlation_id).
    await record_audit(
        actor=actor,
        action=WEBHOOK_SECRET_ROTATED_ACTION,
        resource=str(webhook_uuid),
        result="success",
        correlation_id=correlation_id,
        session=session,
    )
    logger.info(
        "webhook_secret_rotated",
        extra={
            "event": "webhook_secret_rotated",
            "actor": actor,
            "webhook_id": str(webhook_uuid),
            "action": WEBHOOK_SECRET_ROTATED_ACTION,
            "result": "success",
        },
    )

    return WebhookSecretRotation(
        webhook_id=str(webhook_uuid),
        key_id=resolved_key_id,
        secret=material.hex(),
        doc_id=resolved_doc_id,
        room_id=resolved_room_id,
        created=created,
        overlap_until=overlap_until,
    )
