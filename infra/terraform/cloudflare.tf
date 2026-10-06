# =============================================================================
# infra/terraform/cloudflare.tf — borde Cloudflare (T73).
#
# - TLS 1.3 únicamente (TLS 1.2 OFF, sin ventana; OD-09/RNF-01.a).
# - HSTS, HTTPS forzado y modo estricto.
# - WAF gestionado (Cloudflare Managed Ruleset) + reglas propias.
# - Rate limit de borde por IP para `/ingest/webhook` (defensa en profundidad,
#   RNF-12.e) y para `/auth/*`.
# - DNS de la SPA (`dashboard.<dominio-gob>`, Pages) y de la API
#   (`api.<dominio-gob>`, origen FastAPI).
# =============================================================================

resource "cloudflare_zone_settings_override" "edge" {
  zone_id = var.cloudflare_zone_id

  settings {
    ssl                      = "strict"
    min_tls_version          = "1.3"
    tls_1_3                  = "on"
    always_use_https         = "on"
    automatic_https_rewrites = "on"
    opportunistic_encryption = "on"
    security_level           = "high"
    browser_check            = "on"

    security_header {
      enabled            = true
      preload            = true
      include_subdomains = true
      max_age            = 31536000
      nosniff            = true
    }
  }
}

# --- WAF gestionado (execute de los rulesets de Cloudflare) -------------------
resource "cloudflare_ruleset" "waf_managed" {
  zone_id     = var.cloudflare_zone_id
  name        = "excel-sync-gov-managed"
  description = "Ejecuta el WAF gestionado de Cloudflare (sintaxis OWASP + managed)."
  kind        = "zone"
  phase       = "http_request_firewall_managed"

  rules {
    action      = "execute"
    description = "Cloudflare Managed Ruleset"
    enabled     = true
    expression  = "true"

    action_parameters {
      # ID del Cloudflare Managed Ruleset (público, estable).
      id = "efb7b8c949ac4650a09736fc376e9aee"
    }
  }

  rules {
    action      = "execute"
    description = "Cloudflare OWASP Core Ruleset"
    enabled     = true
    expression  = "true"

    action_parameters {
      id = "4814384a9e5d4991b9815dcfc25d2f1f"
    }
  }
}

# --- Reglas propias (métodos y User-Agent de la ingesta) ----------------------
resource "cloudflare_ruleset" "waf_custom" {
  zone_id     = var.cloudflare_zone_id
  name        = "excel-sync-gov-custom"
  description = "Reglas propias del borde para la ingesta firmada."
  kind        = "zone"
  phase       = "http_request_firewall_custom"

  rules {
    action      = "block"
    description = "La ingesta solo admite POST"
    enabled     = true
    expression  = "(http.request.uri.path eq \"/ingest/webhook\" and not http.request.method in {\"POST\"})"
  }

  rules {
    action      = "block"
    description = "La ingesta solo admite el User-Agent declarado por Apps Script"
    enabled     = true
    expression  = "(http.request.uri.path eq \"/ingest/webhook\" and http.user_agent ne \"GoogleAppsScript\")"
  }
}

# --- Rate limit de borde por IP ----------------------------------------------
resource "cloudflare_ruleset" "rate_limit" {
  zone_id     = var.cloudflare_zone_id
  name        = "excel-sync-gov-rate-limit"
  description = "Rate limiting de borde por IP (RNF-12.e)."
  kind        = "zone"
  phase       = "http_ratelimit"

  rules {
    action      = "block"
    description = "Rate limit de /ingest/webhook por IP"
    enabled     = true
    expression  = "(http.request.uri.path eq \"/ingest/webhook\")"

    ratelimit {
      characteristics     = ["ip.src", "cf.colo.id"]
      period              = 60
      requests_per_period = 120
      mitigation_timeout  = 60
    }
  }

  rules {
    action      = "block"
    description = "Rate limit de /auth/* por IP (login/refresh)"
    enabled     = true
    expression  = "(starts_with(http.request.uri.path, \"/auth/\"))"

    ratelimit {
      characteristics     = ["ip.src"]
      period              = 60
      requests_per_period = 60
      mitigation_timeout  = 120
    }
  }
}

# --- DNS ---------------------------------------------------------------------
# SPA en Cloudflare Pages (registro CNAME gestionado por Pages).
resource "cloudflare_record" "dashboard" {
  zone_id = var.cloudflare_zone_id
  name    = var.dashboard_hostname
  type    = "CNAME"
  value   = "excel-sync-gov-dashboard.pages.dev"
  proxied = true
  ttl     = 1
  comment = "SPA (Cloudflare Pages), assets inmutables 1 año"
}

# API detrás del proxy (TLS 1.3 + WAF); el origen FastAPI es privado.
resource "cloudflare_record" "api" {
  zone_id = var.cloudflare_zone_id
  name    = var.api_hostname
  type    = "CNAME"
  value   = "origin.${var.dashboard_hostname}"
  proxied = true
  ttl     = 1
  comment = "Backend FastAPI tras WAF/TLS 1.3"
}
