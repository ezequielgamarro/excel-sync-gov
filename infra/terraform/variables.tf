# =============================================================================
# infra/terraform/variables.tf — variables de entrada (T74).
# Ningún valor por defecto es un secreto. Las credenciales se pasan por entorno
# (TF_VAR_*) o por un `.tfvars` local ignorado por git.
# =============================================================================

variable "project_id" {
  description = "ID del proyecto GCP donde residen Cloud SQL, Memorystore y Secret Manager."
  type        = string
}

variable "region" {
  description = "Región primaria de cómputo/datos (p. ej. southamerica-east1)."
  type        = string
  default     = "southamerica-east1"
}

variable "environment" {
  description = "Entorno lógico (dev | staging | production)."
  type        = string
  default     = "production"
}

variable "db_tier" {
  description = "Tier de Cloud SQL (PostgreSQL gestionado)."
  type        = string
  default     = "db-custom-2-7680"
}

variable "db_name" {
  description = "Nombre de la base de datos del sistema."
  type        = string
  default     = "excel_sync_gov"
}

variable "db_user" {
  description = "Rol de servicio de mínimo privilegio del backend (svc_dashboard)."
  type        = string
  default     = "svc_dashboard"
}

variable "redis_tier" {
  description = "Tier de Memorystore Redis (BASIC | STANDARD_HA)."
  type        = string
  default     = "STANDARD_HA"
}

variable "redis_memory_gb" {
  description = "Memoria de Redis en GB."
  type        = number
  default     = 2
}

variable "backend_service_account_id" {
  description = "Account ID del service account del backend (Workload Identity)."
  type        = string
  default     = "excel-sync-backend"
}

variable "reconciler_service_account_id" {
  description = "Account ID del service account de reconciliación de solo lectura de Google Sheets."
  type        = string
  default     = "excel-sync-sheets-ro"
}

variable "backup_service_account_id" {
  description = "Account ID del service account del dominio de respaldo (solo backups)."
  type        = string
  default     = "excel-sync-backup"
}

variable "jwt_rotation_period" {
  description = "Periodo de rotación de JWT_SIGNING_KEY (90 días = 7776000s, §9.3)."
  type        = string
  default     = "7776000s"
}

variable "webhook_rotation_period" {
  description = "Periodo de rotación del secreto del webhook (90 días, solape 24 h)."
  type        = string
  default     = "7776000s"
}

variable "backup_location" {
  description = "Región del almacén de respaldo, geográficamente separada de la primaria (RNF-14.e)."
  type        = string
  default     = "us-central1"
}

variable "daily_retention_days" {
  description = "Retención de snapshots diarios (RNF-14.c)."
  type        = number
  default     = 35
}

variable "weekly_retention_days" {
  description = "Retención de snapshots semanales (12 semanas)."
  type        = number
  default     = 84
}

variable "monthly_retention_days" {
  description = "Retención de snapshots mensuales (24 meses)."
  type        = number
  default     = 730
}

# --- Cloudflare (T73) --------------------------------------------------------
variable "cloudflare_api_token" {
  description = "Token de API de Cloudflare (sensible; TF_VAR_cloudflare_api_token)."
  type        = string
  sensitive   = true
}

variable "cloudflare_zone_id" {
  description = "Zone ID del dominio gubernamental en Cloudflare."
  type        = string
}

variable "dashboard_hostname" {
  description = "Hostname público del dashboard (SPA)."
  type        = string
  default     = "dashboard.example.gov"
}

variable "api_hostname" {
  description = "Hostname público del backend (api.<dominio-gob>)."
  type        = string
  default     = "api.example.gov"
}
