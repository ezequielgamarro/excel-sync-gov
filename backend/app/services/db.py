"""Capa de persistencia asíncrona (SQLAlchemy async + asyncpg).

Proporciona el motor, la factoría de sesiones y el patrón de acceso que usan las
capas de negocio (F3: ingesta, activación de agentes, auditoría). La URL de
conexión se lee **únicamente** del entorno (``DATABASE_URL``), nunca se hardcodea
(RNF-13). El motor se inicializa de forma perezosa (solo cuando se necesita) y
se cierra en el ``lifespan`` de la app.

Nota de identidad (§2.2.6, docs/schema.md): en producción la lectura del
dashboard usa ``svc_dashboard`` (solo SELECT + auditoría append-only) y la
escritura de ingesta una identidad separada. En F3 se usa ``DATABASE_URL`` para
ambas, dejando el desacople de identidades listo para el despliegue.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Devuelve (creando si hace falta) el motor asíncrono compartido."""
    global _engine, _session_factory
    if _engine is None:
        url = get_settings().database_url
        if not url:
            raise RuntimeError("DATABASE_URL no está definido en el entorno (RNF-13).")
        _engine = create_async_engine(url, pool_pre_ping=True)
        _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Devuelve la factoría de sesiones asíncrona compartida."""
    get_engine()
    assert _session_factory is not None
    return _session_factory


async def get_session() -> AsyncSession:
    """Crea una sesión asíncrona independiente (para auditoría fuera de la request)."""
    return get_session_factory()()


async def dispose_engine() -> None:
    """Cierra el motor (llamado en el shutdown del lifespan)."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None


async def session_dependency() -> AsyncIterator[AsyncSession]:
    """Dependencia FastAPI que entrega una sesión por petición (y la cierra al final)."""
    session = await get_session()
    try:
        yield session
    finally:
        await session.close()
