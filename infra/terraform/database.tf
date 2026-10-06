# =============================================================================
# infra/terraform/database.tf — PostgreSQL gestionado (T74, RNF-06.d).
#
# - Alta disponibilidad con failover: availability_type = "REGIONAL" (réplica
#   síncrona en otra zona) → failover automático.
# - PITR: `point_in_time_recovery_enabled` + WAL continuo (RNF-14.a).
# - Cifrado en tránsito obligatorio (ENCRYPTED_ONLY ⇒ sslmode=verify-full).
# - Backup automático diario con retención 35 días (RNF-14.c).
#
# La contraseña del rol de servicio se genera aleatoriamente y se guarda en
# Secret Manager (secrets.tf), NUNCA en el estado del repositorio.
# =============================================================================

resource "random_password" "svc_dashboard" {
  length           = 48
  special          = true
  override_special = "_-"
}

resource "google_sql_database_instance" "primary" {
  name                = "excel-sync-gov-${var.environment}"
  database_version    = "POSTGRES_16"
  region              = var.region
  deletion_protection = true

  depends_on = [google_service_networking_connection.psa]

  settings {
    tier              = var.db_tier
    availability_type = "REGIONAL" # failover multi-zona (RNF-06.d)
    disk_autoresize   = true
    disk_size         = 20

    backup_configuration {
      enabled                        = true
      start_time                     = "03:00"
      point_in_time_recovery_enabled = true # PITR (RNF-14.a)
      transaction_log_retention_days = 7
      backup_retention_settings {
        retained_backups = var.daily_retention_days
        retention_unit   = "COUNT"
      }
    }

    ip_configuration {
      ipv4_enabled    = false
      private_network = google_compute_network.vpc.id
      # Solo TLS: el backend conecta con sslmode=verify-full (RNF-01.g).
      ssl_mode = "ENCRYPTED_ONLY"
    }

    database_flags {
      name  = "cloudsql.iam_authentication"
      value = "off" # autenticación nativa por usuario/contraseña en app_user
    }

    insights_config {
      query_insights_enabled  = true
      query_string_length     = 1024
      record_application_tags = true
      record_client_address   = false
    }
  }
}

resource "google_sql_database" "app" {
  name     = var.db_name
  instance = google_sql_database_instance.primary.name
}

resource "google_sql_user" "svc_dashboard" {
  name     = var.db_user
  instance = google_sql_database_instance.primary.name
  password = random_password.svc_dashboard.result
}
