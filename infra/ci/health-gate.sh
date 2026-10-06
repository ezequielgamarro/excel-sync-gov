#!/usr/bin/env sh
# =============================================================================
# infra/ci/health-gate.sh — puerta de salud post-deploy (T75, RNF-06).
#
# Espera a que el backend esté listo en el borde. Falla el pipeline si no
# converge, dejando que Swarm aplique el rollback (failure_action=rollback).
#
# Variables:
#   HEALTH_HOST   hostname público (p. ej. api.example.gov)
#   HEALTH_PATH   ruta de liveness (default /health/live)
#   READY_PATH    ruta de readiness interna opcional (default vacío)
#   MAX_ATTEMPTS  sondeos (default 60)
#   SLEEP_SECONDS pausa entre sondeos (default 5)
# =============================================================================
set -eu

: "${HEALTH_HOST:?define HEALTH_HOST}"
HEALTH_PATH="${HEALTH_PATH:-/health/live}"
READY_PATH="${READY_PATH:-}"
MAX_ATTEMPTS="${MAX_ATTEMPTS:-60}"
SLEEP_SECONDS="${SLEEP_SECONDS:-5}"

check() {
    # $1 = url; devuelve 0 si responde 200.
    curl -fsS --max-time 5 "$1" >/dev/null 2>&1
}

attempt=0
while [ "${attempt}" -lt "${MAX_ATTEMPTS}" ]; do
    attempt=$((attempt + 1))
    if check "https://${HEALTH_HOST}${HEALTH_PATH}"; then
        echo "==> Liveness OK: https://${HEALTH_HOST}${HEALTH_PATH} (${attempt})"
        if [ -n "${READY_PATH}" ]; then
            if check "https://${HEALTH_HOST}${READY_PATH}"; then
                echo "==> Readiness OK: https://${HEALTH_HOST}${READY_PATH}"
            else
                echo "    readiness aún no OK; reintentando (${attempt}/${MAX_ATTEMPTS})"
                sleep "${SLEEP_SECONDS}"
                continue
            fi
        fi
        exit 0
    fi
    echo "    sin respuesta (${attempt}/${MAX_ATTEMPTS})"
    sleep "${SLEEP_SECONDS}"
done

echo "ERROR: health gate no convergió para ${HEALTH_HOST}" >&2
exit 1
