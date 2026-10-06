#!/usr/bin/env bash
# =============================================================================
# infra/backup/backup.sh — snapshot cifrado con verificación de integridad (T76).
#
# Cubre RNF-14:
#   - diario/semanal/mensual cifrados, con retención 35 d / 12 semanas / 24 meses
#     (la retención efectiva la aplica el bucket/retention_policy de Terraform);
#   - clave de cifrado DISTINTA de producción (BACKUP_ENCRYPTION_KEY);
#   - incluye el almacén de usuarios locales `app.user_account` (RNF-14.f);
#   - SHA-256 del artefacto cifrado para verificación posterior;
#   - subida a un almacén de respaldo cifrado y geográficamente separado.
#
# Uso:
#   TIER=daily BACKUP_ENCRYPTION_KEY=... DATABASE_URL=... infra/backup/backup.sh
#
# Variables:
#   TIER                    daily | weekly | monthly (default: daily)
#   DATABASE_URL            conexión PostgreSQL (rol con permiso de lectura)
#   BACKUP_ENCRYPTION_KEY   clave de respaldo (independiente de producción)
#   BACKUP_BUCKET_DAILY/WEEKLY/MONTHLY  bucket destino por tier
#   BACKUP_PREFIX           prefijo opcional (default: excel-sync-gov)
# =============================================================================
set -euo pipefail

TIER="${TIER:-daily}"
DATABASE_URL="${DATABASE_URL:?define DATABASE_URL}"
BACKUP_ENCRYPTION_KEY="${BACKUP_ENCRYPTION_KEY:?define BACKUP_ENCRYPTION_KEY (clave distinta de producción)}"
BACKUP_PREFIX="${BACKUP_PREFIX:-excel-sync-gov}"

case "${TIER}" in
    daily)   BACKUP_BUCKET="${BACKUP_BUCKET_DAILY:?define BACKUP_BUCKET_DAILY}" ;;
    weekly)  BACKUP_BUCKET="${BACKUP_BUCKET_WEEKLY:?define BACKUP_BUCKET_WEEKLY}" ;;
    monthly) BACKUP_BUCKET="${BACKUP_BUCKET_MONTHLY:?define BACKUP_BUCKET_MONTHLY}" ;;
    *) echo "ERROR: TIER inválido: ${TIER}" >&2; exit 2 ;;
esac

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
WORKDIR="$(mktemp -d)"
trap 'rm -rf "${WORKDIR}"' EXIT

DUMP="${WORKDIR}/${BACKUP_PREFIX}-${TIER}-${STAMP}.dump"
USERS="${WORKDIR}/${BACKUP_PREFIX}-users-${TIER}-${STAMP}.dump"
ENC="${DUMP}.enc"
SHA_FILE="${ENC}.sha256"

echo "==> [1/4] pg_dump (formato custom) — base completa (incluye app.user_account)"
pg_dump --dbname="${DATABASE_URL}" --format=custom --no-owner --no-privileges \
    --file="${DUMP}"

echo "==> [2/4] pg_dump dirigido del almacén de usuarios (RNF-14.f)"
pg_dump --dbname="${DATABASE_URL}" --format=custom --no-owner --no-privileges \
    --table='app.user_account' --table='app.refresh_token' \
    --file="${USERS}"

echo "==> [3/4] Cifrado AES-256-CBC + PBKDF2 (clave independiente) y checksum"
# La clave se pasa por entorno (no por argumento) para no exponerla en `ps`.
OPENSSL_ENC_ARGS=(-aes-256-cbc -pbkdf2 -iter 600000 -salt -pass env:BACKUP_ENCRYPTION_KEY)
openssl enc "${OPENSSL_ENC_ARGS[@]}" -in "${DUMP}" -out "${ENC}"
# El dump de usuarios se anexa al mismo artefacto lógico vía nombre hermano.
openssl enc "${OPENSSL_ENC_ARGS[@]}" -in "${USERS}" -out "${USERS}.enc"
cat "${ENC}" "${USERS}.enc" > "${ENC}.bundle"
sha256sum "${ENC}.bundle" > "${SHA_FILE}"

echo "==> [4/4] Subida al almacén de respaldo (separado geográficamente)"
DEST="gs://${BACKUP_BUCKET}/${BACKUP_PREFIX}/${TIER}/${STAMP}"
gcloud storage cp "${ENC}.bundle" "${DEST}.enc.bundle"
gcloud storage cp "${SHA_FILE}" "${DEST}.sha256"
gcloud storage cp "${USERS}.enc" "${DEST}.users.enc"

echo "==> Backup ${TIER} OK: ${DEST}.enc.bundle ($(du -h "${ENC}.bundle" | cut -f1))"
