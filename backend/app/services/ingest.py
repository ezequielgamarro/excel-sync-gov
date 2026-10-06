"""Persistencia de la ingesta del webhook (idempotencia + agregados, spec §7.9, T26).

Flujo transaccional tras verificar la firma HMAC (T22/T23), el anti-replay (T24)
y validar esquema/rangos/catálogos (T25):

1. **Advisory lock** por ``event_id`` (serializa duplicados concurrentes).
2. Detección de duplicado: si ``event_id`` ya existe → se devuelve el ``seq``
   previo sin re-aplicar ni redistribuir (idempotencia, RNF-11.a).
3. ``INSERT`` en ``app.ingest_event`` con la identidad del origen
   (``webhook_id``, no un agente), el cuerpo firmado crudo como fuente de verdad
   y la metadata de trazabilidad (``content_sha256``, ``seq``, ``correlation_id``).
4. ``UPSERT`` de ``app.snapshot_current`` (última instantánea por ``doc_id``).
5. Agregados ``agg_hourly`` / ``agg_daily`` (KPIs, regional, turnos) y
   ``ranking_snapshot`` (Top 5 del turno vigente).

La **redistribución por WSS** (fan-out, F4/T28/T29) se publica desde
``app/api/ingest.py`` con ``app/services/bus.py``; aquí solo se persiste el
estado autoritativo en PostgreSQL (fuente del cold start).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import delete, insert, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.tables import (
    CONSULTA_TEXT_COLUMNS,
    KPIS,
    TURNOS,
    agg_daily,
    agg_hourly,
    consulta_event,
    ingest_event,
    ranking_snapshot,
    snapshot_current,
)
from app.services.auth import WebhookIdentity
from app.services.validation import ValidatedSnapshot

logger = get_logger(__name__)


@dataclass(frozen=True)
class IngestResult:
    """Resultado de la persistencia: ``seq`` asignado (o previo) y duplicado."""

    seq: int
    duplicate: bool


async def _next_seq(session: AsyncSession) -> int:
    result = await session.execute(text("SELECT nextval('app.ingest_event_seq')"))
    return int(result.scalar_one())


async def _lock_event(session: AsyncSession, event_id: str) -> None:
    """Serializa el procesamiento de un mismo ``event_id`` (idempotencia dura)."""
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:eid, 0))"),
        {"eid": event_id},
    )


def _ranking_turno(payload: dict[str, Any]) -> str:
    """Determina el turno al que fotografía el ranking (en_curso → último cerrado)."""
    turnos: list[dict[str, Any]] = payload.get("turnos", [])
    for item in turnos:
        if item.get("estado") == "en_curso":
            turno_id: str = item["turno_id"]
            return turno_id
    for item in reversed(turnos):
        if item.get("estado") == "cerrada":
            turno_id = item["turno_id"]
            return turno_id
    return TURNOS[0]


def _to_numeric(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _aggregate_rows(
    validated: ValidatedSnapshot,
    hour_bucket: datetime,
    day_bucket: Any,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    payload = validated.payload
    kpis = payload["kpis"]
    hourly: list[dict[str, Any]] = []
    daily: list[dict[str, Any]] = []

    def add(kpi_id: str, unidad_id: str, turno_id: str, value: int) -> None:
        hourly.append(
            dict(
                bucket=hour_bucket,
                kpi_id=kpi_id,
                unidad_id=unidad_id,
                turno_id=turno_id,
                value=value,
            )
        )
        daily.append(
            dict(
                bucket=day_bucket,
                kpi_id=kpi_id,
                unidad_id=unidad_id,
                turno_id=turno_id,
                value=value,
            )
        )

    for kpi_id in KPIS:
        add(kpi_id, "", "", int(kpis[kpi_id]["value"]))
    for item in payload["regional"]:
        add("intervenciones", item["unidad_id"], "", int(item["intervenciones"]))
    for item in payload["turnos"]:
        add("intervenciones", "", item["turno_id"], int(item["intervenciones"]))
    return hourly, daily


async def _upsert_aggregates(
    session: AsyncSession,
    rows: list[dict[str, Any]],
    table: Any,
) -> None:
    for row in rows:
        stmt = (
            pg_insert(table)
            .values(**row)
            .on_conflict_do_update(
                index_elements=["bucket", "kpi_id", "unidad_id", "turno_id"],
                set_={"value": row["value"], "baseline_value": None},
            )
        )
        await session.execute(stmt)


async def _insert_consultas(
    session: AsyncSession,
    validated: ValidatedSnapshot,
    *,
    seq: int,
    received_at: datetime,
    correlation_id: str,
) -> None:
    """Persiste las filas de la hoja «CONSULTAS» (20 columnas) del evento.

    Idempotente por ``(event_id, row_index, fecha_consulta)``: un reintento del
    mismo evento no duplica filas (``ON CONFLICT DO NOTHING``).
    """
    rows = validated.payload.get("consultas") or []
    for index, row in enumerate(rows):
        fecha_raw = row.get("fecha_consulta")
        try:
            fecha = date.fromisoformat(str(fecha_raw))
        except (ValueError, TypeError):
            continue
        values: dict[str, Any] = {
            "event_id": validated.event_id,
            "doc_id": validated.doc_id,
            "row_index": index,
            "seq": seq,
            "received_at": received_at,
            "correlation_id": correlation_id,
            "fecha_consulta": fecha,
        }
        for column in CONSULTA_TEXT_COLUMNS:
            values[column] = row.get(column) or ""
        stmt = (
            pg_insert(consulta_event)
            .values(**values)
            .on_conflict_do_nothing(index_elements=["event_id", "row_index", "fecha_consulta"])
        )
        await session.execute(stmt)


async def persist_webhook(
    session: AsyncSession,
    *,
    identity: WebhookIdentity,
    validated: ValidatedSnapshot,
    raw_body: bytes,
    correlation_id: str,
) -> IngestResult:
    """Persiste la instantánea aceptada con idempotencia por ``event_id``.

    ``raw_body`` son los bytes crudos ya verificados por la firma y guardados
    como fuente de verdad inmutable del evento (``payload_ciphertext``, §7.9).
    Si ``event_id`` ya fue procesado, no se re-aplica ni se redistribuye.
    """
    event_id = validated.event_id
    webhook_uuid = uuid.UUID(str(identity.webhook_id))
    await _lock_event(session, str(event_id))

    # Idempotencia: si ya existe, devolver el seq previo sin re-aplicar.
    existing = (
        await session.execute(
            select(ingest_event.c.seq).where(ingest_event.c.event_id == event_id).limit(1)
        )
    ).first()
    if existing is not None:
        return IngestResult(seq=int(existing.seq), duplicate=True)

    seq = await _next_seq(session)
    now = datetime.now(timezone.utc)

    # 1. Cabecera inmutable del evento (identidad = webhook_id del origen).
    #    El advisory lock previo evita duplicados concurrentes; el catch de
    #    IntegrityError es la red de seguridad ante carreras residuales.
    try:
        await session.execute(
            insert(ingest_event).values(
                event_id=event_id,
                doc_id=validated.doc_id,
                webhook_id=webhook_uuid,
                content_sha256=validated.content_sha256.lower(),
                payload_ciphertext=raw_body,
                seq=seq,
                received_at=now,
                correlation_id=correlation_id,
            )
        )
    except IntegrityError:
        # event_id ya insertado (carrera residual): devolver el seq previo.
        await session.rollback()
        dup = (
            await session.execute(
                select(ingest_event.c.seq).where(ingest_event.c.event_id == event_id).limit(1)
            )
        ).first()
        if dup is not None:
            return IngestResult(seq=int(dup.seq), duplicate=True)
        raise

    # 2. Última instantánea por doc_id (base del cold start, F4).
    upsert_snapshot = (
        pg_insert(snapshot_current)
        .values(
            doc_id=validated.doc_id,
            event_id=event_id,
            payload=validated.document,
            data_date=validated.data_date,
            seq=seq,
            updated_at=now,
        )
        .on_conflict_do_update(
            index_elements=["doc_id"],
            set_={
                "event_id": event_id,
                "payload": validated.document,
                "data_date": validated.data_date,
                "seq": seq,
                "updated_at": now,
            },
        )
    )
    await session.execute(upsert_snapshot)

    # 3. Agregados horarios/diarios.
    hour_bucket = now.replace(minute=0, second=0, microsecond=0)
    hourly, daily = _aggregate_rows(validated, hour_bucket, validated.data_date)
    await _upsert_aggregates(session, hourly, agg_hourly)
    await _upsert_aggregates(session, daily, agg_daily)

    # 3.b Detalle normalizado de la hoja «CONSULTAS» (20 columnas).
    await _insert_consultas(
        session,
        validated,
        seq=seq,
        received_at=now,
        correlation_id=correlation_id,
    )

    # 4. Ranking Top 5 fotografiado para el turno vigente.
    turno_id = _ranking_turno(validated.payload)
    await session.execute(
        delete(ranking_snapshot).where(
            ranking_snapshot.c.data_date == validated.data_date,
            ranking_snapshot.c.turno_id == turno_id,
        )
    )
    for dep in validated.payload["ranking"]["dependencias"]:
        await session.execute(
            insert(ranking_snapshot).values(
                data_date=validated.data_date,
                turno_id=turno_id,
                puesto=int(dep["puesto"]),
                dependencia_id=dep["dependencia_id"],
                comisaria=dep["comisaria"],
                intervenciones=int(dep["intervenciones"]),
                variacion_abs=dep.get("variacion_abs"),
                variacion_pct=_to_numeric(dep.get("variacion_pct")),
                puesto_previo=dep.get("puesto_previo"),
            )
        )

    return IngestResult(seq=seq, duplicate=False)
