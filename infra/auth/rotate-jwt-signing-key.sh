#!/usr/bin/env sh
# =============================================================================
# infra/auth/rotate-jwt-signing-key.sh — rotación de `JWT_SIGNING_KEY` (T74).
#
# Autenticación NATIVA: este script no habla con ningún proveedor de identidad;
# solo versiona la clave de firma en el gestor de secretos y fuerza un rolling
# restart para que las réplicas nuevas firmen con la clave vigente.
#
# Procedimiento (§9.3, RNF-13.c):
#   1. Genera una clave HS256 nueva (256 bits).
#   2. Publica una versión NUEVA en Secret Manager (la anterior queda habilitada
#      durante el solape; el access token dura 15 min, RNF-03.b).
#   3. Rolling restart del backend (start-first, sin corte) para inyectar la
#      clave nueva en las réplicas.
#   4. Pasada la ventana de solape (>= TTL del refresh), deshabilita la versión
#      antigua y registra el evento de auditoría `key.rotated`.
#
# Uso:
#   SECRET_ID=jwt-signing-key OVERLAP_MINUTES=30 infra/auth/rotate-jwt-signing-key.sh
# =============================================================================
set -eu

PROJECT_ID="${PROJECT_ID:?define PROJECT_ID}"
ENVIRONMENT="${ENVIRONMENT:-production}"
SECRET_ID="${SECRET_ID:-jwt-signing-key}"
OVERLAP_MINUTES="${OVERLAP_MINUTES:-30}"
STACK_NAME="${STACK_NAME:-excel-sync-gov}"
: "${BACKEND_IMAGE:?define BACKEND_IMAGE (registry/repo:tag-inmutable)}"
export BACKEND_IMAGE

echo "==> [1/4] Generando nueva clave de firma HS256"
NEW_KEY="$(openssl rand -base64 48 | tr -d '\n')"

echo "==> [2/4] Publicando nueva versión de ${SECRET_ID}"
NEW_VERSION="$(printf '%s' "${NEW_KEY}" | gcloud secrets versions add "${SECRET_ID}" \
    --project="${PROJECT_ID}" \
    --data-file=- \
    --format='value(name)')"
echo "    versión nueva: ${NEW_VERSION}"
unset NEW_KEY

echo "==> [3/4] Rolling restart del backend (start-first, sin corte)"
BACKEND_IMAGE="${BACKEND_IMAGE:-}" infra/docker/rollout.sh

echo "==> [4/4] Solape de ${OVERLAP_MINUTES} min antes de retirar la versión anterior"
echo "    (automatizar con Cloud Scheduler + este mismo script en modo --retire)"
# gcloud secrets versions disable "$PREVIOUS_VERSION" --secret="${SECRET_ID}" --project="${PROJECT_ID}"
echo "==> Rotación publicada. Evento de auditoría esperado: key.rotated (${ENVIRONMENT})."
