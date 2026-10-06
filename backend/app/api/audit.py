"""Consulta de auditoría ``GET /api/v1/audit/events`` (spec §10.2, T32).

Capacidad ``audit.view``. Devuelve los eventos de la bitácora append-only
(``audit.audit_event``) **sin PII** (la IP ya está seudonimizada en el almacén y
los ``actor``/``resource`` son identificadores opacos; RNF-08.c). Filtros:
``from``/``to`` (rango temporal), ``actor``, ``action`` y ``event_id`` (mapea al
``resource`` de los eventos ``snapshot.accepted``). Paginación ``offset``/``limit``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse

from app.models.tables import audit_event
from app.services.capacity import (
    CAP_AUDIT_VIEW,
    OperatorIdentity,
    get_operator,
    require_capacity,
)
from app.services.db import session_dependency

router = APIRouter(prefix="/audit", tags=["Dashboard"])

_AUDIT_COLUMNS = (
    audit_event.c.ts,
    audit_event.c.actor,
    audit_event.c.action,
    audit_event.c.resource,
    audit_event.c.result,
    audit_event.c.ip,
    audit_event.c.user_agent,
    audit_event.c.correlation_id,
    audit_event.c.schema_version,
)


def _event_to_dict(row: Any) -> dict[str, Any]:
    """Convierte una fila de auditoría a un dict (sin PII)."""
    return {
        "ts": row[0].isoformat() if row[0] is not None else None,
        "actor": row[1],
        "action": row[2],
        "resource": row[3],
        "result": row[4],
        "ip": row[5],
        "user_agent": row[6],
        "correlation_id": row[7],
        "schema_version": row[8],
    }


@router.get("/events")
async def list_events(
    request: Request,
    operator: OperatorIdentity = Depends(get_operator),
    session: AsyncSession = Depends(session_dependency),
    from_: datetime | None = Query(default=None, alias="from"),
    to_: datetime | None = Query(default=None, alias="to"),
    actor: str | None = Query(default=None),
    action: str | None = Query(default=None),
    event_id: str | None = Query(default=None),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=1000),
) -> JSONResponse:
    """Lista eventos de auditoría (capacidad ``audit.view``)."""
    require_capacity(CAP_AUDIT_VIEW, operator)

    conditions: list[Any] = []
    if from_ is not None:
        conditions.append(audit_event.c.ts >= from_)
    if to_ is not None:
        conditions.append(audit_event.c.ts <= to_)
    if actor:
        conditions.append(audit_event.c.actor == actor)
    if action:
        conditions.append(audit_event.c.action == action)
    if event_id:
        # Los eventos de datos guardan el `event_id` en `resource` (snapshot.accepted).
        conditions.append(audit_event.c.resource == event_id)

    stmt = (
        select(*_AUDIT_COLUMNS)
        .where(*conditions)
        .order_by(audit_event.c.ts.desc(), audit_event.c.id.desc())
        .offset(offset)
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    events = [_event_to_dict(row) for row in rows]

    return JSONResponse(
        status_code=200,
        content={
            "events": events,
            "meta": {"count": len(events), "offset": offset, "limit": limit},
        },
    )
