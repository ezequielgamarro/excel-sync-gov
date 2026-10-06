"""Ensamblado de los routers raíz del backend (salud + métricas + negocio + WSS)."""

from __future__ import annotations

from fastapi import APIRouter

from app.api import health, metrics, v1, ws

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(metrics.router)
api_router.include_router(v1.router)
api_router.include_router(ws.router)
