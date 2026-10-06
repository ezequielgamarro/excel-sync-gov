"""Endpoint de ingesta ``POST /api/v1/ingest/webhook`` (spec §10.1, T26).

Origen: el webhook firmado de Google Apps Script. Flujo completo (fail-closed):

1. Lectura de los **bytes crudos** de la petición.
2. Autenticación del origen con ``authenticate_webhook`` (T23): formato de
   cabeceras, ``webhook_id`` activo/no revocado, ``key_id`` vigente, firma
   HMAC-SHA256 en tiempo constante (T22) y **anti-replay** (T24: timestamp ±300 s
   y nonce no visto en 600 s). Todo **antes de deserializar**.
3. Límite de tamaño del cuerpo (RNF-12.f): 256 KB plano / 64 KB comprimido →
   ``413``; después, deserialización a JSON.
4. Validación de esquema/rangos/catálogos (T25).
5. Persistencia idempotente por ``event_id`` (INSERT + UPSERT + agregados) y
   auditoría (aceptado/rechazado con causa).
6. Publicación del evento para redistribución en ``room_id`` (bus de F4).

Respuestas: ``202`` (aceptado) o ``200 {duplicate: true}`` (idempotencia).
"""

from __future__ import annotations

import gzip
import json
import zlib
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse

from app.core.errors import APIError, raise_http_error
from app.core.logging import get_correlation_id, get_logger
from app.core.metrics import INGEST_MAX_PAYLOAD_BYTES
from app.services.audit import record_audit
from app.services.auth import WebhookIdentity, authenticate_webhook
from app.services.bus import publish_snapshot
from app.services.db import session_dependency
from app.services.ingest import IngestResult, persist_webhook
from app.services.source_health import record_webhook_received
from app.services.validation import enforce_size_limit, validate_snapshot

logger = get_logger(__name__)

router = APIRouter(prefix="/ingest", tags=["Ingesta"])

# Codificaciones de transporte soportadas (RNF-12.f mide el cuerpo tal como llega).
_COMPRESSED_ENCODINGS = frozenset({"gzip", "x-gzip", "deflate"})

# Causa auditable por código de rechazo de la capa de autenticación/validación.
_REJECT_CAUSE_BY_CODE: dict[str, str] = {
    "UNAUTHORIZED": "rejected_signature",
    "FORBIDDEN": "rejected_origin",
    "KEY_NOT_ACTIVE": "rejected_key_not_active",
    "ANTI_REPLAY": "rejected_anti_replay",
    "UNAVAILABLE": "rejected_secret_unavailable",
    "PAYLOAD_TOO_LARGE": "rejected_payload_too_large",
    "BAD_REQUEST": "rejected_malformed_body",
    "SNAPSHOT_INVALID": "rejected_snapshot_invalid",
    "DOC_MISMATCH": "rejected_doc_id_mismatch",
}


def _content_encoding(request: Request) -> str:
    """Codificación de contenido declarada (``""`` si es identidad)."""
    raw = (request.headers.get("Content-Encoding") or "").strip().lower()
    return "" if raw in ("", "identity") else raw


def _retries_exhausted_header(request: Request) -> int | None:
    """Reintentos agotados reportados por el origen (salud, T46)."""
    raw = (request.headers.get("X-Webhook-Retries-Exhausted") or "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError:
        return None
    return max(0, value)


def _decode_body(body: bytes, encoding: str) -> bytes:
    """Descomprime el cuerpo si viaja comprimido; ``BAD_REQUEST`` si no se puede."""
    if not encoding:
        return body
    if encoding in ("gzip", "x-gzip"):
        try:
            return gzip.decompress(body)
        except OSError:
            raise_http_error("BAD_REQUEST", "Cuerpo comprimido inválido (gzip).")
    if encoding == "deflate":
        try:
            return zlib.decompress(body)
        except zlib.error:
            try:
                return zlib.decompress(body, -zlib.MAX_WBITS)
            except zlib.error:
                raise_http_error("BAD_REQUEST", "Cuerpo comprimido inválido (deflate).")
    raise_http_error("BAD_REQUEST", "Codificación de contenido no soportada.")


async def _audit_rejection(
    request: Request,
    actor: str,
    cause: str,
    correlation_id: str,
) -> None:
    """Audita un rechazo con causa (sesión propia: sobrevive al rollback).

    Se registra sin sesión de la petición para que el intento quede en la
    bitácora append-only aunque la transacción de negocio no se confirme
    (RNF-08.a). ``record_audit`` nunca propaga su propio fallo.
    """
    await record_audit(
        actor=actor or "unknown",
        action="webhook.rejected",
        resource=cause,
        result="rejected",
        ip=request.client.host if request.client else "",
        user_agent=request.headers.get("User-Agent", ""),
        correlation_id=correlation_id,
    )


@router.post("/webhook")
async def ingest_webhook(
    request: Request,
    session: AsyncSession = Depends(session_dependency),
) -> JSONResponse:
    """Ingesta autenticada de una instantánea del webhook de Apps Script."""
    correlation_id = get_correlation_id()
    actor = (request.headers.get("X-Webhook-Id") or "").strip() or "unknown"
    retries_exhausted = _retries_exhausted_header(request)

    try:
        # 1-2. Bytes crudos + autenticación (firma HMAC + anti-replay) sin parsear.
        body = await request.body()
        # Alerta de payload > 64 KB (RNF-07.d): se registra el máximo observado.
        if len(body) > INGEST_MAX_PAYLOAD_BYTES._value.get():
            INGEST_MAX_PAYLOAD_BYTES.set(len(body))
        identity: WebhookIdentity = await authenticate_webhook(request, session, body=body)
        actor = identity.webhook_id

        # 3. Límite de tamaño antes de deserializar (plano 256 KB / comprimido 64 KB).
        encoding = _content_encoding(request)
        enforce_size_limit(len(body), compressed=bool(encoding))
        decoded = _decode_body(body, encoding)
        try:
            document = json.loads(decoded)
        except (ValueError, UnicodeDecodeError):
            raise_http_error("BAD_REQUEST", "El cuerpo de ingesta no es JSON válido.")

        # 4. Validación de esquema/rangos/catálogos (rechazos de ítem no fatales).
        validated = validate_snapshot(
            document,
            raw_size_bytes=len(body),
            compressed=bool(encoding),
        )

        # Binding origen ↔ documento: un webhook sirve a un único documento.
        if validated.doc_id != identity.doc_id:
            raise_http_error(
                "DOC_MISMATCH",
                "doc_id no corresponde al origen autenticado.",
                status_code=422,
            )

        # 5. Persistencia idempotente (INSERT + UPSERT + agregados).
        result: IngestResult = await persist_webhook(
            session,
            identity=identity,
            validated=validated,
            raw_body=body,
            correlation_id=correlation_id,
        )
    except APIError as exc:
        cause = _REJECT_CAUSE_BY_CODE.get(exc.code, exc.code.lower())
        await _audit_rejection(request, actor, cause, correlation_id)
        raise

    received_at = datetime.now(timezone.utc)
    response_body = {
        "status": "accepted",
        "duplicate": result.duplicate,
        "event_id": str(validated.event_id),
        "seq": result.seq,
        "received_at": received_at.isoformat(),
        "correlation_id": correlation_id,
    }

    # Duplicado: idempotencia pura, sin re-aplicar ni redistribuir (RNF-11.a).
    if result.duplicate:
        await session.rollback()
        # Contacto válido: refresca la salud del origen (T46), sin descartar nada.
        await record_webhook_received(
            session,
            webhook_id=actor,
            result="accepted",
            retries_exhausted=retries_exhausted,
        )
        await session.commit()
        await record_audit(
            actor=actor,
            action="webhook.duplicate",
            resource=str(validated.event_id),
            result="success",
            ip=request.client.host if request.client else "",
            user_agent=request.headers.get("User-Agent", ""),
            correlation_id=correlation_id,
        )
        return JSONResponse(status_code=200, content=response_body)

    # Salud del origen (T46): última recepción aceptada + reintentos agotados.
    await record_webhook_received(
        session,
        webhook_id=actor,
        result="accepted",
        retries_exhausted=retries_exhausted,
    )
    await session.commit()

    # 6. Auditoría de aceptación y de los rechazos de ítem auditables (RF-03.h).
    await record_audit(
        actor=actor,
        action="webhook.accepted",
        resource=str(validated.event_id),
        result="success",
        ip=request.client.host if request.client else "",
        user_agent=request.headers.get("User-Agent", ""),
        correlation_id=correlation_id,
    )
    for rejection in validated.rejections:
        await record_audit(
            actor=actor,
            action="webhook.rejected",
            resource=rejection.code,
            result="rejected",
            ip=request.client.host if request.client else "",
            user_agent=request.headers.get("User-Agent", ""),
            correlation_id=correlation_id,
        )

    # 7. Redistribución (fan-out WSS completo en F4/T28/T29). Si el bus o el
    #    enriquecimiento fallan, la ingesta ya está persistida: se degrada a
    #    polling sin romper la respuesta (RNF-06.e).
    try:
        await publish_snapshot(
            session=session,
            document=validated.document,
            seq=result.seq,
            room_id=identity.room_id,
            webhook_id=identity.webhook_id,
            correlation_id=correlation_id,
            accepted_at=received_at,
        )
    except Exception:
        logger.warning(
            "webhook_publish_failed",
            extra={"event": "webhook_publish", "result": "error"},
        )

    return JSONResponse(status_code=202, content=response_body)
