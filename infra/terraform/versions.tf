# =============================================================================
# infra/terraform/versions.tf — versiones y backend remoto (T73/T74).
#
# Estado remoto cifrado (GCS) para que varios agentes/CI no diverjan. Sustituir
# el bucket por el del entorno antes del primer `terraform init`.
# =============================================================================

terraform {
  required_version = ">= 1.6.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.40"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  backend "gcs" {
    # Bucket de estado remoto (NO contiene secretos; el estado puede contener
    # referencias sensibles, por eso el bucket va cifrado y con acceso mínimo).
    bucket = "REPLACE_ME-terraform-state"
    prefix = "excel-sync-gov"
  }
}
