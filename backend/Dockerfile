# syntax=docker/dockerfile:1.7
# =============================================================================
# backend/Dockerfile — imagen de runtime del backend (Tarea T72, Fase F10).
#
# Objetivos:
#   - Imagen reproducible y mínima (multi-stage; sin toolchain de compilación en
#     la capa final).
#   - Proceso SIN ESTADO en el contenedor: el estado de fan-out/presencia/rate
#     limit vive en Redis y los datos en PostgreSQL (RNF-06.c). No se declaran
#     volúmenes de datos; escalar réplicas es horizontal.
#   - Seguridad: usuario no-root, sistema de ficheros de solo lectura recomendado
#     (`--read-only` + `--tmpfs /tmp`), sin secretos embebidos (RNF-13).
#   - `HEALTHCHECK` sobre `/health/live` para el rolling deploy del orquestador.
#
# Build (contexto = backend/):
#   docker build -t excel-sync-gov-backend:$(git rev-parse --short HEAD) backend/
#
# Run (una réplica; escalar a >=3 con el orquestador):
#   docker run --rm -p 8000:8000 --env-file ../.env excel-sync-gov-backend:latest
# =============================================================================

ARG PYTHON_VERSION=3.12

# -----------------------------------------------------------------------------
# Stage 1 — builder: crea un virtualenv autocontenido con las dependencias.
# -----------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

# Dependencias de compilación (algunas ruedas pueden requerir compilación).
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt ./
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install -r requirements.txt

# -----------------------------------------------------------------------------
# Stage 2 — runtime: solo el virtualenv + el código; usuario no-root.
# -----------------------------------------------------------------------------
FROM python:${PYTHON_VERSION}-slim AS runtime

ARG APP_UID=10001
ARG APP_GID=10001

# OCI (trazabilidad de la imagen).
LABEL org.opencontainers.image.title="excel-sync-gov-backend" \
      org.opencontainers.image.description="Backend FastAPI (REST + WSS) del sistema Google Sheets-to-Web." \
      org.opencontainers.image.licenses="Proprietary" \
      org.opencontainers.image.source="https://github.com/OWNER/excel-sync-gov"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app \
    PATH="/opt/venv/bin:${PATH}" \
    HOST=0.0.0.0 \
    PORT=8000

# libpq5: runtime de psycopg; tini: reaper de PID 1 y reenvío de señales para el
# rolling deploy limpio (SIGTERM → shutdown ordenado del lifespan).
RUN groupadd --gid "${APP_GID}" appuser \
    && useradd --uid "${APP_UID}" --gid "${APP_GID}" \
        --create-home --shell /usr/sbin/nologin appuser \
    && apt-get update \
    && apt-get install -y --no-install-recommends libpq5 tini \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Dependencias (venv) y código de la aplicación. Sin `requirements` de dev ni
# tests (ver .dockerignore).
COPY --from=builder /opt/venv /opt/venv
COPY --chown=appuser:appuser alembic.ini ./
COPY --chown=appuser:appuser alembic ./alembic
COPY --chown=appuser:appuser app ./app
COPY --chown=appuser:appuser scripts ./scripts
COPY --chown=appuser:appuser data ./data

USER appuser

EXPOSE 8000

# Liveness: el proceso responde (no consulta BD/Redis; eso es /health/ready).
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s --retries=3 \
    CMD ["python", "-c", "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=2).status == 200 else 1)"]

ENTRYPOINT ["/usr/bin/tini", "--"]
# Uvicorn con 1 worker por contenedor: la escala es horizontal (≥3 réplicas)
# para compartir el fan-out por Redis (RNF-06.c). TLS lo termina el edge.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
