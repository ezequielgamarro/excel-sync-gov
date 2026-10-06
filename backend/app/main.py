"""Punto de entrada del backend FastAPI (frontera de confianza, Zero Trust).

Ensambla la instancia de FastAPI con el lifespan, la pila de middlewares de
seguridad/observabilidad y los routers. La configuración se lee del entorno
(pydantic-settings) y los secretos nunca se hardcodean (spec §9.5, RNF-13).

Ejecutar desde ``backend/``::

    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Query
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse

from app.api import hospitales
from app.api.router import api_router
from app.config import get_settings
from app.core.csrf import CSRFMiddleware
from app.core.errors import register_exception_handlers
from app.core.logging import CorrelationIdMiddleware, configure_logging, get_logger
from app.core.metrics import MetricsMiddleware
from app.core.rate_limit import RateLimiter, RateLimitMiddleware
from app.core.rbac import RBACMiddleware
from app.core.security import CORSVaryMiddleware, SecurityHeadersMiddleware
from app.core.tracing import TracingMiddleware, configure_tracing
from app.services import excel_policia
from app.services.bus import close_bus
from app.services.db import dispose_engine
from app.services.reconciliation import close_source_supervisor, get_source_supervisor
from app.services.replay import close_replay_guard
from app.services.revocation import close_reauth_registry
from app.services.ticket import close_ticket_store

logger = get_logger(__name__)

#: Orígenes locales de desarrollo habilitados para CORS (frontends Vite/Next).
DEV_CORS_ORIGINS = ("http://localhost:3000", "http://localhost:5173")


def _resolve_excel_url() -> str:
    """Resuelve ``EXCEL_POLICIA_URL`` del entorno (o del ``.env`` de la raíz).

    Se prioriza la variable de entorno (inyectada en producción); como red de
    seguridad para el desarrollo local, si no está definida se carga el ``.env``
    del repositorio con ``python-dotenv`` y se vuelve a consultar.
    """
    url = os.getenv("EXCEL_POLICIA_URL", "").strip()
    if url:
        return url
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - dependencia declarada en requirements
        return ""
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if env_path.is_file():
        load_dotenv(env_path)
    return os.getenv("EXCEL_POLICIA_URL", "").strip()


def create_app() -> FastAPI:
    """Construye y configura la aplicación FastAPI."""
    settings = get_settings()
    configure_logging(settings.log_level)
    # CORS: allowlist exacta configurada, ampliada en desarrollo con los
    # orígenes locales del frontend (Vite 5173 / Next 3000).
    cors_origins = list(settings.cors_origins)
    if settings.environment == "development":
        cors_origins.extend(origin for origin in DEV_CORS_ORIGINS if origin not in cors_origins)
    # Trazas distribuidas (T59): configura el exportador OTLP si el SDK está
    # presente; la propagación W3C/`X-Correlation-Id` funciona igualmente.
    if settings.tracing_enabled:
        configure_tracing(
            settings.otel_service_name,
            settings.otel_exporter_otlp_endpoint,
            insecure=settings.otel_exporter_insecure,
        )

    rate_limiter = RateLimiter(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        logger.info("backend_startup", extra={"event": "startup", "result": settings.environment})
        # Supervisor del origen (F6/T45–T46): reconciliación por polling + salud.
        supervisor = get_source_supervisor() if settings.reconciliation_enabled else None
        if supervisor is not None:
            await supervisor.start()
        yield
        if supervisor is not None:
            await close_source_supervisor()
        await close_replay_guard()
        await close_ticket_store()
        await close_reauth_registry()
        await close_bus()
        await dispose_engine()
        await rate_limiter.close()
        logger.info("backend_shutdown", extra={"event": "shutdown"})

    if settings.enable_docs:
        app = FastAPI(
            title=settings.app_name,
            version="1.0.0",
            lifespan=lifespan,
            docs_url="/docs",
            redoc_url="/redoc",
            openapi_url="/openapi.json",
        )
    else:
        app = FastAPI(
            title=settings.app_name,
            version="1.0.0",
            lifespan=lifespan,
            docs_url=None,
            redoc_url=None,
            openapi_url=None,
        )

    # Orden de middlewares (de fuera a dentro): CORSVary → CORS → Correlation →
    # Tracing → Security → CSRF → Metrics → RateLimit → RBAC → app.
    # ``add_middleware`` inserta al principio, por lo que el último añadido es el
    # más externo. El RBAC queda el más interno (deny por defecto) tras el rate
    # limit; CSRF va por dentro de Security para que sus 403 también reciban las
    # cabeceras de endurecimiento (T63).
    app.add_middleware(RBACMiddleware, enabled=settings.rbac_enabled)
    app.add_middleware(RateLimitMiddleware, settings=settings, limiter=rate_limiter)
    app.add_middleware(MetricsMiddleware, settings=settings)
    app.add_middleware(
        CSRFMiddleware,
        enabled=settings.csrf_enabled,
        secret=settings.csrf_secret or settings.jwt_signing_key,
        header_name=settings.csrf_header_name,
        cors_origins=tuple(cors_origins),
        cookie_samesite=settings.csrf_cookie_samesite,
    )
    app.add_middleware(SecurityHeadersMiddleware, settings=settings)
    app.add_middleware(TracingMiddleware, enabled=settings.tracing_enabled)
    app.add_middleware(CorrelationIdMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        # ``allow_credentials`` solo con allowlist no vacía (§2.2.2, T18).
        allow_credentials=settings.cors_effective_allow_credentials,
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=[
            "Authorization",
            "Content-Type",
            "Accept",
            "X-Correlation-Id",
            settings.csrf_header_name,
        ],
        expose_headers=["X-Correlation-Id", "X-Trace-Id"],
        max_age=600,
    )
    # Normaliza ``Vary: Origin`` (allowlist exacta) en el borde de la pila.
    app.add_middleware(CORSVaryMiddleware, enabled=bool(cors_origins))

    register_exception_handlers(app)
    app.include_router(api_router)
    app.include_router(hospitales.router, prefix="/api/hospitales")

    @app.get("/api/estadisticas", tags=["Estadísticas"])
    async def get_estadisticas(rango: str | None = Query(None)) -> JSONResponse:
        """Métricas reales del workbook de la Policía (``EXCEL_POLICIA_URL``).

        Delega en ``app.services.excel_policia`` la descarga y el parseo de
        todas las hojas relevantes (``DASHBOARD_WEB``, ``CONSULTAS``,
        ``Data``/``ESTADISTICAS``). El parámetro opcional ``rango``
        (``ayer``/``semana``/``mes``/``anio``; ``todo``) recorta la hoja
        ``CONSULTAS`` a una ventana temporal ANTES de calcular las métricas
        (default seguro: ``anio``). Mantiene el contrato histórico
        (``grafico_regionales``, ``grafico_dependencias``, ``alertas_resultados``)
        y añade las series de incidentes, logística y comparativas. Ante
        cualquier fallo responde ``{"estado": "error", "detalle": ...}`` (HTTP 200).
        """
        try:
            url = _resolve_excel_url()
            if not url:
                raise ValueError("La variable de entorno EXCEL_POLICIA_URL no está configurada.")
            content = excel_policia.build_estadisticas(url, rango=rango)
            return JSONResponse(status_code=200, content={"estado": "exito", **content})
        except Exception as exc:  # noqa: BLE001 - se devuelve un error controlado
            return JSONResponse(
                status_code=200,
                content={"estado": "error", "detalle": str(exc)},
            )

    return app


app = create_app()
