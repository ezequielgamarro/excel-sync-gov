"""Endpoint de métricas Prometheus (spec §10.4, RNF-07.c).

``GET /metrics`` expone las métricas del proceso en formato Prometheus. Solo es
accesible desde la **red interna** (se valida la IP del cliente).
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from starlette.responses import Response

from app.core.metrics import render_metrics
from app.core.security import require_internal_network

router = APIRouter(tags=["Salud"])


@router.get("/metrics", include_in_schema=False)
async def metrics_endpoint(request: Request) -> Response:
    """Métricas Prometheus (solo red interna)."""
    require_internal_network(request)
    return render_metrics()
