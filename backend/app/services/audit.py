"""Auditoría append-only (``audit.audit_event``, RNF-08).

Registra acciones sensibles (ingesta aceptada/rechazada, conexión WSS, lectura
de dashboard) en la bitácora inmutable. Cada entrada incluye ``ts`` (UTC),
``actor`` (``sub`` del operador o ``webhook_id`` del origen), ``action``,
``resource``, ``result`` (``success``/``denied``/
``rejected``), ``ip`` **seudonimizada** (hash, RNF-08.c), ``user_agent``,
``correlation_id`` y ``schema_version`` (RNF-08.b).

La auditoría es **append-only** y se escribe de forma independiente (commit
inmediato) para que un rechazo posterior de la transacción de negocio no pierda
el rastro del intento. Nunca registra PII ni secretos.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_correlation_id, get_logger, hash_identifier
from app.models.tables import audit_event
from app.services.db import get_session

logger = get_logger(__name__)

SCHEMA_VERSION = "1.0.0"


def pseudonymize_ip(ip: str) -> str:
    """Seudonimiza una IP (hash truncado); nunca la IP completa (RNF-08.c)."""
    if not ip:
        return ""
    return f"ip-{hash_identifier(ip, length=12)}"


async def record_audit(
    *,
    actor: str,
    action: str,
    resource: str,
    result: str,
    ip: str = "",
    user_agent: str = "",
    correlation_id: str = "",
    schema_version: str = SCHEMA_VERSION,
    session: AsyncSession | None = None,
) -> None:
    """Inserta una entrada de auditoría y la confirma de inmediato.

    Si se pasa ``session`` se usa esa sesión (sin commit, para confirmar junto a
    la transacción de negocio); en caso contrario se abre una sesión propia y se
    confirma en el acto (auditoría durable aunque la transacción principal falle).
    """
    values = {
        "ts": datetime.now(timezone.utc),
        "actor": actor,
        "action": action,
        "resource": resource,
        "result": result,
        "ip": pseudonymize_ip(ip) if ip else None,
        "user_agent": user_agent[:200] if user_agent else None,
        "correlation_id": correlation_id or get_correlation_id(),
        "schema_version": schema_version,
    }
    own_session = session is None
    target: AsyncSession
    if session is not None:
        target = session
    else:
        target = await get_session()
    try:
        await target.execute(insert(audit_event).values(**values))
        if own_session:
            await target.commit()
    except Exception:
        # La auditoría no debe tumbar el flujo principal, pero sí se registra el fallo.
        logger.exception("audit_write_failed", extra={"event": "audit", "result": "error"})
        if own_session:
            await target.rollback()
    finally:
        if own_session:
            await target.close()
