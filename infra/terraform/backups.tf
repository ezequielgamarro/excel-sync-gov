# =============================================================================
# infra/terraform/backups.tf — respaldo y recuperación (T76, RNF-14).
#
# - Clave de cifrado de backups DISTINTA de la de producción (RNF-14.c).
# - Almacén cifrado y geográficamente separado (RNF-14.e), acceso solo del rol
#   de servicio de respaldo.
# - Retención: diarios 35 d · semanales 12 semanas (84 d) · mensuales 24 meses
#   (730 d) (RNF-14.c).
# - Incluye el almacén de usuarios locales (`app.user_account`) en el backup
#   diario cifrado (RNF-14.f).
# - PITR + failover del PostgreSQL están en database.tf (RNF-14.a/b).
# =============================================================================

resource "google_kms_key_ring" "backup" {
  name     = "excel-sync-gov-backup-${var.environment}"
  location = var.backup_location
}

# Clave de respaldo independiente de la clave de producción (RNF-14.c).
resource "google_kms_crypto_key" "backup" {
  name            = "backup-encryption-key"
  key_ring        = google_kms_key_ring.backup.id
  rotation_period = "7776000s" # 90 días
  purpose         = "ENCRYPT_DECRYPT"

  lifecycle {
    prevent_destroy = true
  }
}

locals {
  backup_buckets = {
    daily   = { retention_days = var.daily_retention_days, storage_class = "STANDARD" }
    weekly  = { retention_days = var.weekly_retention_days, storage_class = "NEARLINE" }
    monthly = { retention_days = var.monthly_retention_days, storage_class = "COLDLINE" }
  }
}

resource "google_storage_bucket" "backups" {
  for_each                    = local.backup_buckets
  name                        = "excel-sync-gov-backup-${each.key}-${var.environment}"
  location                    = var.backup_location # geográficamente separado
  storage_class               = each.value.storage_class
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  versioning {
    enabled = true
  }

  encryption {
    default_kms_key_name = google_kms_crypto_key.backup.id
  }

  retention_policy {
    is_locked        = true
    retention_period = each.value.retention_days * 86400
  }

  lifecycle_rule {
    condition {
      age = each.value.retention_days
    }
    action {
      type = "Delete"
    }
  }

  lifecycle_rule {
    condition {
      num_newer_versions = 3
      with_state         = "ARCHIVED"
    }
    action {
      type = "Delete"
    }
  }

  labels = {
    app         = "excel-sync-gov"
    environment = var.environment
    tier        = each.key
    purpose     = "disaster-recovery"
  }
}

# Solo el rol de servicio de respaldo escribe/lee el almacén (RNF-14.e).
resource "google_storage_bucket_iam_member" "backup_writer" {
  for_each = google_storage_bucket.backups
  bucket   = each.value.name
  role     = "roles/storage.objectAdmin"
  member   = "serviceAccount:${google_service_account.backup.email}"
}

# El backend NO tiene acceso al almacén de backups (separación de funciones).
