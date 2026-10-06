# =============================================================================
# infra/terraform/observability.tf — observabilidad de producción (T77).
#
# - Synthetic checks POR MINUTO contra los healthchecks públicos y el cold start.
# - Políticas de alerta alineadas con RNF-07.d.
# - Canal de notificación (rotado; sin secretos en el repo).
#
# El stack Prometheus/Grafana y sus dashboards/reglas viven en
# `infra/observability/` (aprovisionamiento versionado).
# =============================================================================

resource "google_monitoring_notification_channel" "oncall" {
  display_name = "On-call dashboard (${var.environment})"
  type         = "email"

  labels = {
    email_address = "oncall-dashboard@example.gov"
  }

  # Se recomienda sustituir por el receptor real (PagerDuty/Slack) del entorno.
}

# --- Synthetic checks por minuto ---------------------------------------------
resource "google_monitoring_uptime_check_config" "health_live" {
  display_name = "Synthetic: /health/live por minuto"
  timeout      = "10s"
  period       = "60s" # por minuto (RNF-06.a)

  http_check {
    path         = "/health/live"
    port         = 443
    use_ssl      = true
    validate_ssl = true
    request_method = "GET"
  }

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.project_id
      host       = var.api_hostname
    }
  }
}

resource "google_monitoring_uptime_check_config" "cold_start" {
  display_name = "Synthetic: cold start /dashboard/snapshot por minuto"
  timeout      = "10s"
  period       = "60s"

  http_check {
    path         = "/dashboard/snapshot"
    port         = 443
    use_ssl      = true
    validate_ssl = true
    request_method = "GET"
  }

  monitored_resource {
    type = "uptime_url"
    labels = {
      project_id = var.project_id
      host       = var.api_hostname
    }
  }
}

# --- Políticas de alerta (RNF-07.d) ------------------------------------------
resource "google_monitoring_alert_policy" "health_failing" {
  display_name = "Uptime: healthcheck fallando"
  combiner     = "OR"
  severity     = "CRITICAL"

  conditions {
    display_name = "Synthetic check en rojo"
    condition_threshold {
      filter          = "metric.type=\"monitoring.googleapis.com/uptime_check/check_passed\" AND resource.type=\"uptime_url\""
      comparison      = "COMPARISON_LT"
      threshold_value = 1
      duration        = "120s"
      aggregations {
        alignment_period   = "60s"
        per_series_aligner = "ALIGN_NEXT_OLDER"
        cross_series_reducer = "REDUCE_COUNT_TRUE"
      }
    }
  }

  notification_channels = [google_monitoring_notification_channel.oncall.id]
  alert_strategy {
    auto_close = "1800s"
  }
}

resource "google_monitoring_alert_policy" "wss_connections_zero" {
  display_name = "WSS: 0 conexiones con sala activa"
  combiner     = "OR"
  severity     = "CRITICAL"

  conditions {
    display_name = "Conexiones WSS activas = 0"
    condition_threshold {
      filter          = "metric.type=\"custom.googleapis.com/excel_sync/wss_connections_active\" AND resource.type=\"generic_task\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"
    }
  }

  notification_channels = [google_monitoring_notification_channel.oncall.id]
}

resource "google_monitoring_alert_policy" "webhook_stale" {
  display_name = "Ingesta: último webhook > 5 min"
  combiner     = "OR"
  severity     = "WARNING"

  conditions {
    display_name = "Sin recepción de webhook"
    condition_threshold {
      filter          = "metric.type=\"custom.googleapis.com/excel_sync/webhook_seconds_since_last\" AND resource.type=\"generic_task\""
      comparison      = "COMPARISON_GT"
      threshold_value = 300
      duration        = "0s"
    }
  }

  notification_channels = [google_monitoring_notification_channel.oncall.id]
}
