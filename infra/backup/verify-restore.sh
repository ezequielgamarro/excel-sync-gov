#!/usr/bin/env bash
# =============================================================================
# infra/backup/verify-restore.sh — verificación de checksum y ensayo de
# restauración (T76, RNF-14.d/f).
#
# Pasos:
#   1. Descarga el snapshot cifrado y su SHA-256.
#   2. Verifica el checksum (RNF-14.d) — falla si no coincide.
#   3. Descifra con la clave de respaldo (independiente de producción).
#   4. Restaura en una base de datos *scratch* (no toca producción).
#   5. Comprueba la integridad funcional del almacén de usuarios
#      (app.user_account) y de la auditoría.
#
# Debe ejecutarse al menos TRIMESTRALMENTE (documentar fecha/resultado en el
# registro de ensayos). Región separada, rol de servicio de respaldo.
#
# Uso:
#   BACKUP_URI=gs://bucket/excel-sync-gov/daily/20260101T030000Z.enc.bundle \
#   SCRATCH_DATABASE_URL=postgresql://... \
#   BACKUP_ENCRYPTION_KEY=... infra/backup/verify-restore.sh
# =============================================================================
set -euo pipefail

BACKUP_URI="${BACKUP_URI:?define BACKUP_URI (ruta gs:// del snapshot)}"
SCRATCH_DATABASE_URL="${SCRATCH_DATABASE_URL:?define SCRATCH_DATABASE_URL (base de ensayo, NO producción)}"
BACKUP_ENCRYPTION_KEY="${BACKUP_ENCRYPTION_KEY:?define BACKUP_ENCRYPTION_KEY}"

WORKDIR="$(mktemp -d)"
trap 'rm -rf "${WORKDIR}"' EXIT

BUNDLE="${WORKDIR}/snapshot.enc.bundle"
SHA_FILE="${WORKDIR}/snapshot.sha256"

echo "==> [1/5] Descarga del snapshot y su checksum"
gcloud storage cp "${BACKUP_URI}" "${BUNDLE}"
gcloud storage cp "${BACKUP_URI%.enc.bundle}.sha256" "${SHA_FILE}" || \
    gcloud storage cp "${BACKUP_URI}.sha256" "${SHA_FILE}"

echo "==> [2/5] Verificación de integridad (SHA-256)"
expected="$(awk '{print $1}' "${SHA_FILE}")"
actual="$(sha256sum "${BUNDLE}" | awk '{print $1}')"
if [ -z "${expected}" ] || [ "${expected}" != "${actual}" ]; then
    echo "ERROR: checksum NO coincide — backup corrupto (RNF-14.d)" >&2
    exit 1
fi
echo "    checksum OK (${actual})"

echo "==> [3/5] Descifrado con la clave de respaldo"
openssl enc -d -aes-256-cbc -pbkdf2 -iter 600000 \
    -pass env:BACKUP_ENCRYPTION_KEY \
    -in "${BUNDLE}" -out "${WORKDIR}/restore.dump"

echo "==> [4/5] Restauración en base de ensayo"
pg_restore --clean --if-exists --no-owner --no-privileges \
    --dbname="${SCRATCH_DATABASE_URL}" "${WORKDIR}/restore.dump"

echo "==> [5/5] Comprobación funcional (almacén de usuarios y auditoría)"
psql "${SCRATCH_DATABASE_URL}" -v ON_ERROR_STOP=1 -c \
    "SELECT count(*) AS usuarios FROM app.user_account;" \
    -c "SELECT count(*) AS refresh_tokens FROM app.refresh_token;" \
    -c "SELECT count(*) AS eventos_auditoria FROM audit.audit_event;"

echo "==> Ensayo de restauración OK. Registrar fecha y resultado (RNF-14.d)."
