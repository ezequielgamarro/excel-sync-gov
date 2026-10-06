"""Endpoint admin de provisión/rotación del secreto del webhook (spec §10.1, T27).

``POST /api/v1/admin/webhook/secret/rotate`` — capacidad
``platform.manage_webhook`` (**deny-by-default**, §2.2.3, RNF-03.c):

- ``webhook_id`` ausente ⇒ **alta nueva** (se genera un ``webhook_id`` UUIDv7);
  requiere ``doc_id``. ``webhook_id`` presente ⇒ **rotación** del origen activo.
- Genera un ``key_id`` versionado y un **secreto de 256 bits** que se devuelve
  **una sola vez** (nunca se relee por la API ni se guarda en la BD). El material
  se deposita en el secret manager; la BD solo conserva metadata
  (``webhook_registry``/``webhook_secret``), §9.2–§9.5, RNF-02.e.
- La rotación mantiene un **solape de 24 h** entre la versión entrante y la
  saliente (§9.3).
- Se audita ``platform.webhook.secret_rotated`` (actor = ``sub`` y
  ``correlation_id``) y, ante rechazo, ``platform.webhook.secret_rotate_rejected``.

Migrado del endpoint antiguo de activación de agentes (retirado en el pivote a
Google Sheets + Apps Script, T16/T27): ya no se emiten credenciales de agente;
la identidad del origen se verifica por firma HMAC-SHA256.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse

from app.core.errors import APIError
from app.core.logging import get_correlation_id
from app.services.agents import rotate_webhook_secret
from app.services.audit import record_audit
from app.services.capacity import (
    CAP_PLATFORM_MANAGE_WEBHOOK,
    OperatorIdentity,
    get_operator,
    require_capacity,
)
from app.services.db import session_dependency

router = APIRouter(prefix="/webhook", tags=["Admin"])

_REJECTED = "platform.webhook.secret_rotate_rejected"


class WebhookSecretRotateRequest(BaseModel):
    """Cuerpo opcional: alta nueva (``doc_id``) o rotación (``webhook_id``)."""

    webhook_id: str | None = Field(
        default=None,
        max_length=64,
        description="Origen existente a rotar; ausente ⇒ alta nueva (UUIDv7).",
    )
    doc_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=256,
        description="Documento de Google Sheets del origen (obligatorio en alta).",
    )
    room_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
        description="Sala servida por el origen (opcional; por defecto la canónica).",
    )
    key_id: str | None = Field(
        default=None,
        max_length=64,
        description="key_id versionado sugerido (opcional; se genera si falta).",
    )


@router.post("/secret/rotate", status_code=201)
async def rotate_secret(
    request: Request,
    body: WebhookSecretRotateRequest,
    operator: OperatorIdentity = Depends(get_operator),
    session: AsyncSession = Depends(session_dependency),
) -> JSONResponse:
    """Provisiona o rota el secreto del webhook (se muestra una sola vez)."""
    correlation_id = get_correlation_id()
    try:
        # Deny-by-default: sin la capacidad, 403 sin revelar nada (AM-01).
        require_capacity(CAP_PLATFORM_MANAGE_WEBHOOK, operator)
        result = await rotate_webhook_secret(
            session,
            actor=operator.sub,
            correlation_id=correlation_id,
            webhook_id=body.webhook_id,
            doc_id=body.doc_id,
            room_id=body.room_id,
            key_id=body.key_id,
        )
        await session.commit()
    except APIError as exc:
        await session.rollback()
        await record_audit(
            actor=operator.sub,
            action=_REJECTED,
            resource=exc.code,
            result="rejected",
            ip=request.client.host if request.client else "",
            user_agent=request.headers.get("User-Agent", ""),
            correlation_id=correlation_id,
        )
        raise

    # El ``secret`` se muestra UNA sola vez (jamás se vuelve a leer ni se registra).
    return JSONResponse(
        status_code=201,
        content={
            "webhook_id": result.webhook_id,
            "key_id": result.key_id,
            "secret": result.secret,
            "doc_id": result.doc_id,
            "room_id": result.room_id,
            "created": result.created,
            "overlap_until": result.overlap_until.isoformat() if result.overlap_until else None,
            "message": (
                "Guarde el secreto en Script Properties del Apps Script; "
                "no se volverá a mostrar."
            ),
        },
    )
