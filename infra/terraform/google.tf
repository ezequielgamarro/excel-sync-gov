# =============================================================================
# infra/terraform/google.tf — integración Google Sheets y Workload Identity (T74).
#
# La reconciliación por polling de respaldo (RF-01.i, RNF-06.f) usa un service
# account de SOLO LECTURA sobre el documento de la cuenta Gmail estándar. No hay
# escritura ni acceso a otros recursos de Google.
# =============================================================================

# El documento de Sheets se comparte como LECTOR con este service account
# (fuera de Terraform, en Google Drive). Aquí solo se crea la identidad.
# Recomendación: sin roles de proyecto; el permiso del documento es suficiente.

# Pool de identidad de cargas: el backend asume su service account sin claves
# JSON de larga vida en disco. El emisor/atributos concretos se configuran en el
# despliegue según la plataforma (ver README); el secreto `google-service-account`
# solo se usa como respaldo en entornos sin identidad federada.
resource "google_iam_workload_identity_pool" "backend" {
  workload_identity_pool_id = "excel-sync-backend-pool"
  display_name              = "Pool de identidad de cargas del backend"
  description               = "Permite al backend asumir su service account sin claves estáticas."
}

resource "google_service_account_iam_member" "backend_workload_identity" {
  service_account_id = google_service_account.backend.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.backend.name}/*"
}

# El reconciliador solo necesita leer la hoja; el permiso se otorga en Drive.
# Se expone su email para la configuración manual documentada en el README.
