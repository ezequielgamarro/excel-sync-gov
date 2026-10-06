"""Autenticación del webhook de Apps Script (firma HMAC-SHA256, spec §2.2.1, §9, T23).

El origen es el webhook de Google Apps Script. El backend autentica cada
``POST /ingest/webhook`` verificando, **en este orden estricto y antes de
deserializar el cuerpo** (fail-closed):

1. Presencia y **formato** de las cabeceras ``X-Webhook-Id``,
   ``X-Webhook-Key-Id``, ``X-Webhook-Nonce``, ``X-Webhook-Timestamp`` y
   ``X-Webhook-Signature`` (más ``X-Webhook-Version``), vía la primitiva de T22.
2. ``webhook_id`` existe en ``webhook_registry``, está **activo** y **no
   revocado**.
3. ``key_id`` **vigente** en ``webhook_secret`` (con solape de rotación de 24 h).
4. **Firma HMAC-SHA256 válida** sobre la cadena canónica §9.2, con comparación en
   tiempo constante (primitiva de T22); el material del secreto se resuelve del
   secret manager, nunca de la BD.
5. Frescura temporal y anti-replay (T24): ``X-Webhook-Timestamp`` dentro de
   ±300 s y ``X-Webhook-Nonce`` no visto en la ventana de 600 s (cache Redis),
   con ``409`` (``ANTI_REPLAY``) ante desalineación o repetición y auditoría del
   intento. Se delega en ``app.services.replay.enforce_replay``.

La BD solo aporta **metadata** (``webhook_registry``/``webhook_secret``); el
material del secreto vive en el secret manager (§9.2, RNF-02.e).

Códigos (spec §2.2.1, §10.1, §10.5): desconocido / firma inválida → ``401``;
inactivo, revocado o ``key_id`` no vigente → ``403``; repetición de nonce o
desalineación temporal en la ingesta → ``409``. Los mensajes de autenticación
son genéricos y **no filtran detalle** (qué cabecera, qué comparación falló).

Fuera de alcance: orquestación del endpoint ``POST /ingest/webhook`` (T26).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import raise_http_error
from app.core.logging import get_logger
from app.models.tables import webhook_registry, webhook_secret
from app.services.db import session_dependency
from app.services.replay import ReplayGuard, enforce_replay
from app.services.webhook_signature import (
    EnvironmentSecretManager,
    SecretManager,
    WebhookSecretMetadata,
    parse_signed_headers,
    verify_webhook_signature,
)

logger = get_logger(__name__)

# Mensajes genéricos: un rechazo no debe distinguir la causa concreta ni filtrar
# qué cabecera o comparación falló (anti-enumeración, §2.2.1/§10.1).
_GENERIC_UNAUTHORIZED = "Origen no autenticado."
_GENERIC_FORBIDDEN = "Origen no autorizado."


@dataclass(frozen=True)
class WebhookIdentity:
    """Identidad verificada del webhook, disponible para el handler de ingesta.

    Incluye el ``key_id`` usado para firmar y la metadata de origen
    (``doc_id``/``room_id``) resuelta de ``webhook_registry``.
    """

    webhook_id: str
    key_id: str
    doc_id: str
    room_id: str
    nonce: str
    timestamp: datetime
    version: str
    schema_version: str
    content_sha256: str


def _webhook_uuid(webhook_id: str) -> uuid.UUID:
    """Convierte el ``X-Webhook-Id`` al UUID con el que se indexa la BD.

    Un valor que no sea UUID no puede existir en ``webhook_registry``: se
    rechaza como origen desconocido (``401``) sin consultar la base de datos.
    """
    try:
        return uuid.UUID(webhook_id)
    except (ValueError, AttributeError, TypeError):
        raise_http_error("UNAUTHORIZED", _GENERIC_UNAUTHORIZED)


async def _active_webhook(session: AsyncSession, webhook_uuid: uuid.UUID) -> tuple[str, str]:
    """Comprueba que el origen existe, está activo y no revocado (paso 2).

    Devuelve ``(doc_id, room_id)``. Desconocido → ``401``; inactivo o revocado →
    ``403`` (spec §2.2.1, §10.1).
    """
    result = await session.stream(
        select(
            webhook_registry.c.estado,
            webhook_registry.c.revoked_at,
            webhook_registry.c.doc_id,
            webhook_registry.c.room_id,
        ).where(webhook_registry.c.webhook_id == webhook_uuid)
    )
    row = await result.fetchone()
    if row is None:
        raise_http_error("UNAUTHORIZED", _GENERIC_UNAUTHORIZED)
    if row.estado != "activo" or row.revoked_at is not None:
        raise_http_error("FORBIDDEN", _GENERIC_FORBIDDEN)
    return str(row.doc_id), str(row.room_id)


async def _secret_candidates(
    session: AsyncSession, webhook_uuid: uuid.UUID
) -> list[WebhookSecretMetadata]:
    """Metadata de las versiones del secreto del origen (solo metadata, §9.2).

    El **material** no se lee de la BD; se devuelve ``key_id`` + estado +
    ventana ``not_before``/``not_after``. La selección de la versión vigente y el
    solape de rotación los resuelve la primitiva de T22.
    """
    result = await session.stream(
        select(
            webhook_secret.c.key_id,
            webhook_secret.c.webhook_id,
            webhook_secret.c.estado,
            webhook_secret.c.not_before,
            webhook_secret.c.not_after,
        ).where(webhook_secret.c.webhook_id == webhook_uuid)
    )
    rows = await result.fetchall()
    return [
        WebhookSecretMetadata(
            key_id=str(row.key_id),
            webhook_id=str(row.webhook_id),
            estado=str(row.estado),
            not_before=row.not_before,
            not_after=row.not_after,
        )
        for row in rows
    ]


async def authenticate_webhook(
    request: Request,
    session: AsyncSession,
    *,
    body: bytes,
    secret_manager: SecretManager | None = None,
    now: datetime | None = None,
    replay_guard: ReplayGuard | None = None,
) -> WebhookIdentity:
    """Ejecuta la cadena de autenticación del webhook (fail-closed).

    ``body`` son los **bytes crudos** de la petición: se usan para recomputar la
    firma, pero **nunca se deserializan** aquí. El orden de los pasos es el de
    spec §2.2.1 y cualquier fallo corta antes del siguiente.
    """
    # 1. Presencia y formato de las cabeceras (sin tocar el cuerpo).
    parsed = parse_signed_headers(request.headers)

    # 2. webhook_id existe, activo y no revocado.
    webhook_uuid = _webhook_uuid(parsed.webhook_id)
    doc_id, room_id = await _active_webhook(session, webhook_uuid)

    # 3. key_id vigente (metadata) + 4. firma HMAC-SHA256 válida. La primitiva
    #    de T22 resuelve la versión vigente, comprueba el binding del origen,
    #    resuelve el secreto del secret manager y compara en tiempo constante.
    verified = verify_webhook_signature(
        body=body,
        headers=request.headers,
        metadata_candidates=await _secret_candidates(session, webhook_uuid),
        secret_manager=secret_manager if secret_manager is not None else EnvironmentSecretManager(),
        now=now,
    )

    identity = WebhookIdentity(
        webhook_id=verified.webhook_id,
        key_id=verified.key_id,
        doc_id=doc_id,
        room_id=room_id,
        nonce=verified.nonce,
        timestamp=verified.timestamp,
        version=verified.version,
        schema_version=verified.schema_version,
        content_sha256=verified.content_sha256,
    )

    # 5. Anti-replay (T24): timestamp ±300 s y nonce no visto (cache 600 s),
    #    antes de deserializar/persistir. Reutiliza la identidad verificada.
    await enforce_replay(
        identity,
        request=request,
        session=session,
        now=now,
        guard=replay_guard,
    )

    return identity


async def get_webhook_identity(
    request: Request,
    session: AsyncSession = Depends(session_dependency),
) -> WebhookIdentity:
    """Dependencia FastAPI: autentica el webhook y devuelve la identidad verificada.

    Lee los bytes crudos (``await request.body()``) sin deserializarlos; la
    validación de esquema/rangos es responsabilidad de T25/T26.
    """
    body = await request.body()
    return await authenticate_webhook(request, session, body=body)
