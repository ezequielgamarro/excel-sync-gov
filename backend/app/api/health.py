"""Healthchecks (spec §10.4, RNF-06, RNF-07.c, RNF-14.g).

- ``GET /health/live``: liveness del proceso (público en el edge), siempre 200.
- ``GET /health/ready``: readiness (BD + Redis accesibles), solo red interna;
  devuelve 200 o 503 con cuerpo de error uniforme.

La comprobación de BD usa SQLAlchemy (motor asíncrono ``postgresql+asyncpg://``,
el mismo esquema de ``DATABASE_URL`` que las migraciones), y la de Redis usa
``redis.asyncio``.
"""

from __future__ import annotations

import asyncio

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from starlette.responses import JSONResponse

from app.config import get_settings
from app.core.errors import build_error_body
from app.core.security import require_internal_network
from app.services.alerts import collect_metrics_snapshot, get_alert_registry
from app.services.db import session_dependency
from app.services.source_health import alert_signals

router = APIRouter(tags=["Salud"])

# Timeout corto por dependencia: una dependencia lenta no debe colgar el sondeo
# de readiness (el orquestador decide con base en un resultado acotado).
HEALTH_CHECK_TIMEOUT_S = 3.0


@router.get("/health/live")
async def health_live() -> dict[str, str]:
    """Liveness: el proceso está vivo (siempre 200). Público en el edge."""
    return {"status": "ok"}


async def _database_ready(url: str) -> bool:
    if not url:
        return False
    engine = create_async_engine(url, connect_args={"timeout": HEALTH_CHECK_TIMEOUT_S})
    try:
        async with asyncio.timeout(HEALTH_CHECK_TIMEOUT_S):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False
    finally:
        await engine.dispose()


async def _redis_ready(url: str) -> bool:
    if not url:
        return False
    client = aioredis.from_url(url, socket_connect_timeout=2.0, socket_timeout=2.0)
    try:
        async with asyncio.timeout(HEALTH_CHECK_TIMEOUT_S):
            return bool(await client.ping())
    except Exception:
        return False
    finally:
        await client.aclose()


@router.get("/health/ready")
async def health_ready(request: Request) -> JSONResponse:
    """Readiness: BD + Redis accesibles (200) o no (503). Solo red interna."""
    require_internal_network(request)
    settings = get_settings()
    db_ok, redis_ok = await asyncio.gather(
        _database_ready(settings.database_url),
        _redis_ready(settings.redis_url),
    )
    if db_ok and redis_ok:
        return JSONResponse(status_code=200, content={"status": "ok"})
    return JSONResponse(
        status_code=503,
        content=build_error_body("UNAVAILABLE", "Backend no listo: dependencias no disponibles."),
    )


@router.get("/health/alerts", include_in_schema=False)
async def health_alerts(
    request: Request,
    session: AsyncSession = Depends(session_dependency),
) -> JSONResponse:
    """Alertas configuradas activas (RNF-07.d, T60). **Solo red interna**.

    Evalúa las reglas sobre las métricas Prometheus y la salud del origen, y
    publica ``alert_active`` por regla. No es un endpoint público (P7).
    """
    require_internal_network(request)
    settings = get_settings()
    registry = get_alert_registry()
    if not settings.alerts_enabled:
        return JSONResponse(status_code=200, content={"enabled": False, "active": []})

    try:
        stale_seconds, retries_exhausted = await alert_signals(session)
    except Exception:
        # Sin BD no se pierde el resto de la evaluación (degrada con elegancia).
        stale_seconds, retries_exhausted = None, None
    snapshot = collect_metrics_snapshot(
        settings=settings,
        room_active=bool(settings.default_room_id),
        webhook_seconds_since_last=stale_seconds,
        webhook_retries_exhausted=retries_exhausted,
    )
    active = registry.evaluate(snapshot)
    return JSONResponse(
        status_code=200,
        content={
            "enabled": True,
            "active": [alert.as_dict() for alert in active],
            "rules": [
                {
                    "name": rule.name,
                    "threshold": rule.threshold,
                    "severity": rule.severity,
                    "description": rule.description,
                }
                for rule in registry.rules
            ],
        },
    )
