# =============================================================================
# infra/terraform/outputs.tf — salidas de la infraestructura (T74).
# Las salidas sensibles quedan marcadas como tales (no se imprimen en claro).
# =============================================================================

output "sql_instance_connection_name" {
  description = "Nombre de conexión de Cloud SQL (para el proxy/Workload Identity)."
  value       = google_sql_database_instance.primary.connection_name
}

output "sql_private_ip" {
  description = "IP privada de PostgreSQL (el backend conecta con sslmode=verify-full)."
  value       = google_sql_database_instance.primary.private_ip_address
}

output "redis_host" {
  description = "Host de Memorystore Redis (TLS + AUTH)."
  value       = google_redis_instance.bus.host
}

output "redis_port" {
  description = "Puerto TLS de Redis."
  value       = google_redis_instance.bus.port
}

output "backend_service_account_email" {
  description = "Email del service account del backend (Workload Identity)."
  value       = google_service_account.backend.email
}

output "reconciler_service_account_email" {
  description = "Email del service account de solo lectura de Google Sheets (compartir el documento como LECTOR)."
  value       = google_service_account.reconciler.email
}

output "backup_service_account_email" {
  description = "Email del rol de servicio de respaldo."
  value       = google_service_account.backup.email
}

output "secret_ids" {
  description = "IDs de los secretos en Secret Manager (los valores se inyectan en runtime)."
  value       = [for secret in google_secret_manager_secret.app : secret.secret_id]
}

output "backup_bucket_names" {
  description = "Buckets de respaldo cifrado (diario/semanal/mensual)."
  value       = [for bucket in google_storage_bucket.backups : bucket.name]
}

output "backup_kms_key" {
  description = "Clave KMS de respaldo (independiente de producción)."
  value       = google_kms_crypto_key.backup.id
  sensitive   = true
}
