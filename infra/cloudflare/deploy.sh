#!/usr/bin/env sh
# =============================================================================
# infra/cloudflare/deploy.sh — publica la SPA en Cloudflare Pages (T73).
#
# La SPA se despliega SIEMPRE ANTES que el backend (ventana de 2 minors, §7.8):
# el cliente nuevo tolera/capaz de operar sin el backend nuevo. Ver el pipeline
# `.github/workflows/deploy.yml` (job `deploy-spa` antes de `deploy-backend`).
#
# Requisitos: Node + npm; credenciales en el entorno (NUNCA en el repo, RNF-13):
#   CLOUDFLARE_API_TOKEN     token con permisos Pages
#   CLOUDFLARE_ACCOUNT_ID    id de cuenta
#   PAGES_PROJECT_NAME       (default: excel-sync-gov-dashboard)
#   PAGES_BRANCH             (default: production)
#   VITE_API_BASE_URL        origen público de la API (config no secreta)
# =============================================================================
set -eu

ROOT_DIR="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
cd "${ROOT_DIR}"

: "${CLOUDFLARE_API_TOKEN:?define CLOUDFLARE_API_TOKEN}"
: "${CLOUDFLARE_ACCOUNT_ID:?define CLOUDFLARE_ACCOUNT_ID}"
: "${VITE_API_BASE_URL:?define VITE_API_BASE_URL (origen público de la API)}"

PAGES_PROJECT_NAME="${PAGES_PROJECT_NAME:-excel-sync-gov-dashboard}"
PAGES_BRANCH="${PAGES_BRANCH:-production}"

echo "==> Build de la SPA (assets con hash)"
npm --prefix dashboard ci
npm --prefix dashboard run build

# Verificación de política de caché/seguridad antes de publicar.
test -f dashboard/dist/_headers || { echo "ERROR: falta dashboard/dist/_headers" >&2; exit 1; }
test -f dashboard/dist/_redirects || { echo "ERROR: falta dashboard/dist/_redirects" >&2; exit 1; }

echo "==> Deploy a Cloudflare Pages (${PAGES_PROJECT_NAME}/${PAGES_BRANCH})"
CLOUDFLARE_ACCOUNT_ID="${CLOUDFLARE_ACCOUNT_ID}" \
    npx --yes wrangler@3 pages deploy dashboard/dist \
        --project-name "${PAGES_PROJECT_NAME}" \
        --branch "${PAGES_BRANCH}" \
        --commit-dirty=true

echo "==> SPA publicada. Assets inmutables 1 año (Cache-Control: immutable)."
