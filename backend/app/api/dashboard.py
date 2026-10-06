"""Lectura del operador: cold start, histórico y export CSV (spec §10.2, T30/T31).

- ``GET /dashboard/snapshot`` — cold start (p95 ≤ 800 ms, RNF-04.c). Lee
  ``snapshot_current`` de PostgreSQL; **funciona sin Redis** (RNF-06.e). Si Redis
  está disponible y su ``seq`` espejado es mayor que el persistido, responde
  ``409`` («hay un snapshot más nuevo vía WSS», §10.4).
- ``GET /dashboard/history`` — serie temporal de agregados (``hour``/``day``),
  rango ≤ 90 días (supervisor) / 60 meses (auditor) según capacidades.
- ``GET /dashboard/export.csv`` — CSV de agregados con cabecera de auditoría
  (marcas de agua) y ``Cache-Control: no-store`` (AM-09). Requiere capacidad
  ``dash.export.csv`` (capacidad auditada, RNF-03.g).
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.responses import JSONResponse, Response

from app.config import get_settings
from app.core.errors import raise_http_error
from app.core.logging import get_correlation_id
from app.models.tables import (
    KPIS,
    REGIONAL_UNITS,
    TURNOS,
    agg_daily,
    agg_hourly,
    consulta_event,
    snapshot_current,
)
from app.services.aggregate import canonical_tz, enrich_payload
from app.services.audit import record_audit
from app.services.bus import attach_freshness_quality, build_snapshot_message, get_bus
from app.services.capacity import (
    CAP_AUDIT_VIEW,
    CAP_DASH_EXPORT_CSV,
    CAP_DASH_VIEW_HISTORY,
    CAP_DASH_VIEW_LIVE,
    OperatorIdentity,
    get_operator,
    require_capacity,
)
from app.services.db import session_dependency
from app.services.read_audit import record_first_view

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


async def _load_current_snapshot(session: AsyncSession) -> Any | None:
    """Devuelve la fila más reciente de ``snapshot_current`` (o ``None``)."""
    return (
        await session.execute(
            select(snapshot_current).order_by(snapshot_current.c.updated_at.desc()).limit(1)
        )
    ).first()


@router.get("/snapshot")
async def get_snapshot(
    request: Request,
    operator: OperatorIdentity = Depends(get_operator),
    session: AsyncSession = Depends(session_dependency),
    tz: str = Query(default=""),
    room_id: str = Query(default=""),
) -> JSONResponse:
    """Cold start: última instantánea aceptada (sobre ``indicators.snapshot``)."""
    require_capacity(CAP_DASH_VIEW_LIVE, operator)
    settings = get_settings()
    room = room_id or settings.default_room_id

    row = await _load_current_snapshot(session)
    if row is None:
        raise_http_error("UNAVAILABLE", "No hay snapshot disponible todavía.", status_code=503)

    # 409 informativo (§10.4): si Redis espeja un seq más nuevo que el persistido,
    # hay un snapshot circulando por WSS que este cold start aún no refleja.
    live_seq = await get_bus().get_last_seq(room)
    if live_seq is not None and live_seq > int(row.seq):
        raise_http_error(
            "CONFLICT",
            "Hay un snapshot más nuevo disponible vía WSS.",
            status_code=409,
        )

    document: dict[str, Any] = dict(row.payload or {})
    data_date = row.data_date
    accepted_at: datetime = row.updated_at
    effective_tz = tz or str(document.get("tz") or settings.canonical_timezone)

    payload = await enrich_payload(
        session,
        document.get("payload") or {},
        data_date=data_date,
        as_of=accepted_at,
    )
    payload = attach_freshness_quality(
        payload,
        sheet_modified_at=str(document.get("sheet_modified_at") or ""),
        accepted_at=accepted_at,
    )
    message = build_snapshot_message(
        document=document,
        seq=int(row.seq),
        room_id=room,
        # Origen del evento (webhook de Google Sheets). La columna histórica
        # `snapshot_current.agent_id` almacena el `webhook_id` del origen.
        webhook_id=str(row.agent_id) if row.agent_id else "",
        correlation_id=get_correlation_id(),
        payload=payload,
        accepted_at=accepted_at,
        tz=effective_tz,
    )

    await record_first_view(
        sub=operator.sub,
        room_id=room,
        data_date=str(data_date),
        event_id=str(row.event_id),
        ip=request.client.host if request.client else "",
        user_agent=request.headers.get("User-Agent", ""),
    )
    return JSONResponse(status_code=200, content=message)


def _history_max_days(operator: OperatorIdentity) -> int:
    """Rango máximo de histórico según capacidades (§10.2, OD-07)."""
    settings = get_settings()
    if CAP_AUDIT_VIEW in operator.capabilities:
        return settings.history_auditor_max_days
    return settings.history_supervisor_max_days


async def _query_history(
    session: AsyncSession,
    table: Any,
    start: Any,
    end: Any,
    unit: str | None,
) -> list[dict[str, Any]]:
    conds = [table.c.bucket >= start, table.c.bucket <= end, table.c.turno_id == ""]
    if unit:
        conds.append(or_(table.c.kpi_id.in_(KPIS), table.c.unidad_id == unit))
    stmt = (
        select(table.c.bucket, table.c.kpi_id, table.c.unidad_id, table.c.value)
        .where(*conds)
        .order_by(table.c.bucket)
    )
    rows = (await session.execute(stmt)).all()

    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        bucket = row[0]
        kpi_id = row[1]
        unidad_id = row[2]
        value = row[3]
        key = bucket.isoformat() if hasattr(bucket, "isoformat") else str(bucket)
        point = grouped.setdefault(key, {"ts": key, "kpis": {}, "regional": []})
        if kpi_id in KPIS:
            point["kpis"][kpi_id] = int(value)
        elif kpi_id == "intervenciones" and unidad_id in REGIONAL_UNITS:
            point["regional"].append({"unidad_id": unidad_id, "intervenciones": int(value)})
    return [grouped[key] for key in sorted(grouped)]


@router.get("/history")
async def get_history(
    request: Request,
    operator: OperatorIdentity = Depends(get_operator),
    session: AsyncSession = Depends(session_dependency),
    from_: datetime = Query(alias="from"),
    to_: datetime = Query(alias="to"),
    bucket: str = Query(),
    unit: str | None = Query(default=None),
    timezone_: str = Query(default="", alias="timezone"),
) -> JSONResponse:
    """Histórico de agregados (bucket ``hour``/``day``)."""
    require_capacity(CAP_DASH_VIEW_HISTORY, operator)

    if bucket not in ("hour", "day"):
        raise_http_error("BAD_REQUEST", "Parámetro 'bucket' debe ser 'hour' o 'day'.")
    if unit is not None and unit not in REGIONAL_UNITS:
        raise_http_error("BAD_REQUEST", "Unidad regional fuera del catálogo.")

    if from_ > to_:
        raise_http_error("BAD_REQUEST", "Rango inválido: 'from' es posterior a 'to'.")
    max_days = _history_max_days(operator)
    if (to_ - from_).days > max_days:
        raise_http_error(
            "BAD_REQUEST",
            f"Rango histórico máximo permitido: {max_days} días.",
        )

    if bucket == "hour":
        series = await _query_history(session, agg_hourly, from_, to_, unit)
    else:
        series = await _query_history(session, agg_daily, from_.date(), to_.date(), unit)

    await record_audit(
        actor=operator.sub,
        action="dashboard.history.read",
        resource=bucket,
        result="success",
        ip=request.client.host if request.client else "",
        user_agent=request.headers.get("User-Agent", ""),
    )
    return JSONResponse(
        status_code=200,
        content={"series": series, "meta": {"bucket": bucket, "count": len(series)}},
    )


_CONSULTA_RANGO_DAYS: dict[str, int] = {"24h": 1, "7d": 7, "30d": 30}


def _consulta_date_bounds(rango: str) -> tuple[date, date]:
    """Rango de fechas [desde, hasta] en la zona canónica para el filtro global."""
    days = _CONSULTA_RANGO_DAYS[rango]
    today = datetime.now(timezone.utc).astimezone(canonical_tz()).date()
    return today - timedelta(days=days - 1), today


async def _consulta_total(session: AsyncSession, conds: list[Any]) -> int:
    stmt = select(func.count()).select_from(consulta_event).where(*conds)
    return int((await session.execute(stmt)).scalar_one())


async def _consulta_groups(
    session: AsyncSession,
    column: Any,
    conds: list[Any],
    *,
    limit: int = 12,
) -> list[dict[str, Any]]:
    """Agrupa por ``column`` (Resultado/Causas/Jefatura/Turno) y cuenta filas."""
    stmt = (
        select(column, func.count().label("value"))
        .where(*conds)
        .group_by(column)
        .order_by(func.count().desc())
        .limit(limit)
    )
    rows = (await session.execute(stmt)).all()
    groups: list[dict[str, Any]] = []
    for row in rows:
        raw = str(row[0]).strip() if row[0] is not None else ""
        groups.append(
            {
                "key": raw,
                "label": raw or "(sin dato)",
                "value": int(row[1]),
            }
        )
    return groups


async def _consulta_series(session: AsyncSession, conds: list[Any]) -> list[dict[str, Any]]:
    stmt = (
        select(consulta_event.c.fecha_consulta, func.count().label("value"))
        .where(*conds)
        .group_by(consulta_event.c.fecha_consulta)
        .order_by(consulta_event.c.fecha_consulta)
    )
    rows = (await session.execute(stmt)).all()
    return [{"ts": row[0].isoformat(), "value": int(row[1])} for row in rows if row[0] is not None]


@router.get("/consultas")
async def get_consultas(
    request: Request,
    operator: OperatorIdentity = Depends(get_operator),
    session: AsyncSession = Depends(session_dependency),
    turno: str = Query(default=""),
    unidad: str = Query(default=""),
    resultado: str = Query(default=""),
    causa: str = Query(default=""),
    rango: str = Query(default="24h"),
) -> JSONResponse:
    """Agregación real de la hoja «CONSULTAS» según los filtros globales.

    Alimenta los gráficos (torta por Resultado, barras por Jefatura Regional y
    Turno) y los KPIs derivados de la agrupación (Total Consultas, Personas
    Aprehendidas, etc.). Requiere capacidad ``dash.view.live``.
    """
    require_capacity(CAP_DASH_VIEW_LIVE, operator)

    if rango not in _CONSULTA_RANGO_DAYS:
        raise_http_error("BAD_REQUEST", "Parámetro 'rango' debe ser '24h', '7d' o '30d'.")
    turno_norm = turno.strip().upper()
    if turno_norm and turno_norm not in TURNOS:
        raise_http_error("BAD_REQUEST", "Turno fuera del catálogo.")
    unidad_norm = unidad.strip()
    if unidad_norm and unidad_norm.lower() not in REGIONAL_UNITS:
        raise_http_error("BAD_REQUEST", "Unidad regional fuera del catálogo.")

    date_from, date_to = _consulta_date_bounds(rango)
    conds: list[Any] = [
        consulta_event.c.fecha_consulta >= date_from,
        consulta_event.c.fecha_consulta <= date_to,
    ]
    if turno_norm:
        conds.append(consulta_event.c.turno == turno_norm)
    if unidad_norm:
        conds.append(func.lower(consulta_event.c.jefatura_regional).contains(unidad_norm.lower()))
    if resultado.strip():
        conds.append(consulta_event.c.resultado.ilike(f"%{resultado.strip()}%"))
    if causa.strip():
        conds.append(consulta_event.c.causas_penales.ilike(f"%{causa.strip()}%"))

    total = await _consulta_total(session, conds)
    by_resultado = await _consulta_groups(session, consulta_event.c.resultado, conds)
    by_causas = await _consulta_groups(session, consulta_event.c.causas_penales, conds)
    by_jefatura = await _consulta_groups(session, consulta_event.c.jefatura_regional, conds)
    by_turno = await _consulta_groups(session, consulta_event.c.turno, conds)
    series = await _consulta_series(session, conds)

    personas_conds = conds + [
        or_(
            consulta_event.c.resultado.ilike("%APREHEN%"),
            consulta_event.c.resultado.ilike("%DETENID%"),
            consulta_event.c.resultado.ilike("%DETENCI%"),
        )
    ]
    vehiculos_conds = conds + [consulta_event.c.tipo_arma_vehiculo.ilike("%VEH%")]
    armas_conds = conds + [consulta_event.c.tipo_arma_vehiculo.ilike("%ARMA%")]

    payload = {
        "meta": {
            "rango": rango,
            "turno": turno_norm,
            "unidad": unidad_norm,
            "resultado": resultado.strip(),
            "causa": causa.strip(),
            "total": total,
        },
        "kpis": {
            "total_consultas": total,
            "personas_aprehendidas": await _consulta_total(session, personas_conds),
            "vehiculos_secuestrados": await _consulta_total(session, vehiculos_conds),
            "armas_secuestradas": await _consulta_total(session, armas_conds),
        },
        "by_resultado": by_resultado,
        "by_causas_penales": by_causas,
        "by_jefatura_regional": by_jefatura,
        "by_turno": by_turno,
        "series": series,
    }

    await record_audit(
        actor=operator.sub,
        action="dashboard.consultas.read",
        resource=f"{rango}:{turno_norm}:{unidad_norm}",
        result="success",
        ip=request.client.host if request.client else "",
        user_agent=request.headers.get("User-Agent", ""),
        correlation_id=get_correlation_id(),
    )
    return JSONResponse(status_code=200, content=payload)


def _build_csv(
    payload: dict[str, Any],
    *,
    sub: str,
    event_id: str,
    room_id: str,
) -> str:
    """Construye el CSV de agregados con cabecera de auditoría (marcas de agua)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    ts = datetime.now(timezone.utc).isoformat()
    writer.writerow([f"# generado_por={sub};event_id_base={event_id};ts={ts};sala={room_id}"])
    writer.writerow(["seccion", "clave", "label", "valor", "variacion_abs", "variacion_pct"])

    for kpi_id in KPIS:
        kpi = payload.get("kpis", {}).get(kpi_id, {})
        writer.writerow(
            [
                "kpi",
                kpi_id,
                kpi.get("label", ""),
                kpi.get("value", ""),
                kpi.get("delta_abs", ""),
                kpi.get("delta_pct", ""),
            ]
        )
    for item in payload.get("regional", []):
        writer.writerow(
            [
                "regional",
                item.get("unidad_id", ""),
                item.get("label", ""),
                item.get("intervenciones", ""),
                item.get("variacion_abs", ""),
                item.get("variacion_pct", ""),
            ]
        )
    for item in payload.get("turnos", []):
        writer.writerow(
            [
                "turno",
                item.get("turno_id", ""),
                item.get("label", ""),
                item.get("intervenciones", ""),
                item.get("variacion_abs", ""),
                item.get("variacion_pct", ""),
            ]
        )
    for dep in payload.get("ranking", {}).get("dependencias", []):
        writer.writerow(
            [
                "ranking",
                dep.get("puesto", ""),
                dep.get("comisaria", ""),
                dep.get("intervenciones", ""),
                dep.get("variacion_abs", ""),
                dep.get("variacion_pct", ""),
            ]
        )
    return buffer.getvalue()


@router.get("/export.csv")
async def export_csv(
    request: Request,
    operator: OperatorIdentity = Depends(get_operator),
    session: AsyncSession = Depends(session_dependency),
) -> Response:
    """Exportación CSV de agregados (capacidad ``dash.export.csv``, auditada).

    La acción sensible exige la capacidad y queda auditada.
    """
    require_capacity(CAP_DASH_EXPORT_CSV, operator)
    settings = get_settings()

    row = await _load_current_snapshot(session)
    if row is None:
        raise_http_error("UNAVAILABLE", "No hay snapshot disponible todavía.", status_code=503)

    document: dict[str, Any] = dict(row.payload or {})
    room = settings.default_room_id
    payload = await enrich_payload(
        session,
        document.get("payload") or {},
        data_date=row.data_date,
        as_of=row.updated_at,
    )
    csv_text = _build_csv(
        payload,
        sub=operator.sub,
        event_id=str(row.event_id),
        room_id=room,
    )

    await record_audit(
        actor=operator.sub,
        action="export.csv",
        resource=str(row.event_id),
        result="success",
        ip=request.client.host if request.client else "",
        user_agent=request.headers.get("User-Agent", ""),
        correlation_id=get_correlation_id(),
    )
    return Response(
        content=csv_text,
        media_type="text/csv; charset=utf-8",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": 'attachment; filename="export.csv"',
        },
    )
