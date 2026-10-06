# =============================================================================
# infra/terraform/redis.tf — Redis gestionado (T74, RNF-06.c).
#
# Redis es DESCARTABLE (RNF-14.b): pub/sub de fan-out, presencia y rate limit
# distribuido. Se aprovisiona con alta disponibilidad (STANDARD_HA) y cifrado en
# tránsito + AUTH para que las réplicas del backend compartan el estado.
# =============================================================================

resource "google_redis_instance" "bus" {
  name               = "excel-sync-gov-${var.environment}"
  tier               = var.redis_tier # STANDARD_HA ⇒ réplica + failover
  memory_size_gb     = var.redis_memory_gb
  region             = var.region
  redis_version      = "REDIS_7_0"
  display_name       = "excel-sync-gov bus (pub/sub, presencia, rate limit)"
  authorized_network = google_compute_network.vpc.id

  # Seguridad en tránsito y autenticación (el backend usa rediss:// con AUTH).
  auth_enabled            = true
  transit_encryption_mode = "SERVER_AUTHENTICATION"

  # Persistencia mínima de cortesía; Redis es reconstruible desde PostgreSQL.
  persistence_config {
    persistence_mode    = "RDB"
    rdb_snapshot_period = "ONE_HOUR"
  }

  maintenance_policy {
    weekly_maintenance_window {
      day = "SUNDAY"
      start_time {
        hours   = 4
        minutes = 0
      }
    }
  }

  labels = {
    app         = "excel-sync-gov"
    environment = var.environment
    disposable  = "true"
  }
}
