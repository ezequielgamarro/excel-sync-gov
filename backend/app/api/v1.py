"""Routers de negocio bajo ``/api/v1``.

Mapeo con el contrato (§10):

- ``ingest_router``   → ``POST /api/v1/ingest/webhook`` (F3, webhook Apps Script).
- ``dashboard_router``→ ``GET /api/v1/dashboard/snapshot|history|export.csv`` (F4).
- ``audit_router``    → ``GET /api/v1/audit/events`` (F4).
- ``auth_router``     → ``POST /api/v1/auth/login|refresh|logout`` (F5, auth nativa).
- ``ws.auth_router``  → ``POST /api/v1/auth/ws-ticket`` (F4, ticket WSS).
- ``admin_router``    → ``/api/v1/admin/webhook/secret/rotate`` (T27) y gestión de
  usuarios/roles locales (F5, ``platform.manage_users``).

El WebSocket ``/ws/dashboard`` vive en la raíz (``app/api/ws.py``), no bajo
``/api/v1`` (ver OpenAPI §10.3).

Nota (pivote a Google Sheets + Apps Script): ``app/api/agents.py`` (antigua
activación de agentes, retirada) ahora expone la **provisión/rotación del
secreto del webhook** (T27) bajo ``admin_router``.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api import admin, agents, audit, auth, dashboard, ingest, ws

router = APIRouter(prefix="/api/v1")

admin_router = APIRouter(prefix="/admin", tags=["Admin"])

router.include_router(ingest.router)
router.include_router(dashboard.router)
router.include_router(audit.router)
router.include_router(auth.router)
router.include_router(ws.auth_router)
admin_router.include_router(agents.router)
admin_router.include_router(admin.router)
router.include_router(admin_router)
