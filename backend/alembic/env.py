"""Entorno de ejecución de Alembic (backend).

Zero Trust (spec §9.5, RNF-13): la URL de conexión se lee ÚNICAMENTE de la
variable de entorno ``DATABASE_URL``. Nunca se hardcodea, nunca se registra y
nunca se versiona. El motor asíncrono usa ``asyncpg`` (coincide con el stack
runtime de FastAPI y con ``DATABASE_URL=postgresql+asyncpg://`` de
``backend/.env.example``).

Ejecutar desde ``backend/``:

    alembic upgrade head      # aplicar todas las migraciones
    alembic downgrade -1      # revertir la última
    alembic upgrade head --sql  # emitir SQL sin conectar (modo offline)
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig
from typing import Optional

from alembic import context
from sqlalchemy import MetaData, pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Objeto Config de Alembic (acceso a los valores del .ini).
config = context.config

# Configura el logging a partir de alembic.ini.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# URL de conexión desde el entorno (fail-closed si no está definida).
# ---------------------------------------------------------------------------
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL no está definido en el entorno. "
        "Defínelo (ver backend/.env.example) antes de ejecutar Alembic."
    )
config.set_main_option("sqlalchemy.url", DATABASE_URL)

# ---------------------------------------------------------------------------
# Metadatos de los modelos (para autogenerate).
# T7 no define modelos: las tablas llegan en T8–T14 como migraciones escritas
# a mano (no autogenerate). Cuando existan los modelos SQLAlchemy del backend,
# importarlos aquí y asignar `target_metadata = Base.metadata`.
# ---------------------------------------------------------------------------
target_metadata: Optional[MetaData] = None


def run_migrations_offline() -> None:
    """Emite el SQL sin conectar (modo offline, ``alembic ... --sql``)."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Configura y ejecuta las migraciones sobre una conexión síncrona."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Crea un engine asíncrono (asyncpg) y ejecuta las migraciones sobre él."""
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Conecta a la base de datos y ejecuta las migraciones."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
