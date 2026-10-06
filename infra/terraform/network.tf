# =============================================================================
# infra/terraform/network.tf — red privada y acceso privado a servicios (T74).
#
# Cloud SQL (IP privada) y Memorystore viven en la VPC del proyecto; el backend
# los alcanza por la red interna. No se exponen a Internet.
# =============================================================================

resource "google_compute_network" "vpc" {
  name                    = "excel-sync-gov-${var.environment}"
  auto_create_subnetworks = false
  routing_mode            = "REGIONAL"
}

resource "google_compute_subnetwork" "app" {
  name          = "excel-sync-gov-${var.environment}-app"
  region        = var.region
  network       = google_compute_network.vpc.id
  ip_cidr_range = "10.20.0.0/24"
  private_ip_google_access = true
}

# Rango reservado para el peering de Private Service Access (Cloud SQL/Redis).
resource "google_compute_global_address" "private_service_range" {
  name          = "excel-sync-gov-${var.environment}-psa"
  purpose       = "VPC_PEERING"
  address_type  = "INTERNAL"
  prefix_length = 16
  network       = google_compute_network.vpc.id
}

resource "google_service_networking_connection" "psa" {
  network                 = google_compute_network.vpc.id
  service                 = "servicenetworking.googleapis.com"
  reserved_peering_ranges = [google_compute_global_address.private_service_range.name]
}
