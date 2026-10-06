# =============================================================================
# infra/terraform/providers.tf — proveedores (T74).
#
# Credenciales NUNCA en el repo (RNF-13): el provider de Google usa
# `application_default_credentials` / Workload Identity; el de Cloudflare recibe
# el token por variable (TF_VAR_cloudflare_api_token o -var-file local ignorado
# por git).
# =============================================================================

provider "google" {
  project = var.project_id
  region  = var.region
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}
