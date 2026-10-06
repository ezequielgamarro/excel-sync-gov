#!/usr/bin/env sh
# =============================================================================
# infra/docker/rollout.sh — rolling deploy sin corte (T72, RNF-06.c).
#
# Flujo atómico y reversible:
#   1. Construye/publica la imagen con tag INMUTABLE (git SHA).
#   2. Despliega el stack. Swarm aplica `order: start-first`: levanta una réplica
#      nueva, espera su healthcheck y solo entonces retira una antigua.
#   3. Espera convergencia (todas las réplicas healthy) y falla en caso contrario
#      (Swarm ya dispara `failure_action: rollback`).
#
# Requisitos: Docker + Swarm inicializado, gestor de secretos disponible para
# exportar las variables de entorno (los valores NUNCA se escriben en disco).
#
# Uso:
#   BACKEND_IMAGE=registry/excel-sync-gov-backend:$(git rev-parse --short HEAD) \
#     infra/docker/rollout.sh
# =============================================================================
set -eu

STACK_NAME="${STACK_NAME:-excel-sync-gov}"
COMPOSE_FILE="${COMPOSE_FILE:-infra/docker/docker-stack.prod.yml}"
HEALTH_PATH="${HEALTH_PATH:-/health/live}"

: "${BACKEND_IMAGE:?define BACKEND_IMAGE (registry/repo:tag-inmutable)}"
export BACKEND_IMAGE

echo "==> Rolling deploy de ${STACK_NAME} (${BACKEND_IMAGE})"
docker stack deploy -c "${COMPOSE_FILE}" "${STACK_NAME}"

echo "==> Esperando convergencia del servicio backend (start-first, sin corte)"
attempts=0
max_attempts=60
while [ "${attempts}" -lt "${max_attempts}" ]; do
    # `docker service ls` expone "running/desired" (p. ej. 3/3).
    replicas="$(docker service ls \
        --filter "name=${STACK_NAME}_backend" \
        --format '{{.Replicas}}' 2>/dev/null | head -n1)"
    running="${replicas%/*}"
    desired="${replicas#*/}"
    echo "    réplicas=${replicas:-0/0} (${attempts}/${max_attempts})"
    if [ -n "${replicas}" ] && [ "${running}" = "${desired}" ] && [ "${desired}" != "0" ]; then
        echo "==> Deploy OK: ${replicas} réplicas en running."
        exit 0
    fi
    attempts=$((attempts + 1))
    sleep 5
done

echo "ERROR: el servicio no convergió; revisa 'docker service ps ${STACK_NAME}_backend'" >&2
echo "       (Swarm aplica rollback automático con failure_action=rollback)" >&2
exit 1
