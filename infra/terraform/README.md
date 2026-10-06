# IaC — PostgreSQL gestionado, Redis, secretos y borde (T74)

Infraestructura como código (Terraform) del sistema. **Autenticación nativa**:
no se aprovisiona ningún proveedor de identidad externo. Los usuarios locales
viven en PostgreSQL (`app.user_account`, hash Argon2id) y la firma de los JWT se
custodia en Secret Manager.

## Recursos

| Fichero | Recursos |
|---------|----------|
| `versions.tf` | Versiones de Terraform/proveedores y backend remoto GCS. |
| `providers.tf` | Providers `google` y `cloudflare` (credenciales por entorno). |
| `network.tf` | VPC, subred y *private service access*. |
| `database.tf` | **Cloud SQL PostgreSQL 16**: `availability_type=REGIONAL` (failover), **PITR**, TLS obligatorio (`ENCRYPTED_ONLY`), backups diarios 35 d. |
| `redis.tf` | **Memorystore Redis** (STANDARD_HA) con TLS + AUTH; descartable. |
| `secrets.tf` | **Secret Manager**: `jwt-signing-key`, `webhook-secret`, `database-url`, `redis-url`, `csrf-secret`, KEK/DEK, claves de backup, `google-service-account`; rotación de JWT/webhook cada 90 días y service accounts del backend/reconciliador/respaldo. |
| `google.tf` | Service account de **solo lectura** de Google Sheets (reconciliación) y Workload Identity. |
| `backups.tf` | KMS propio + buckets cifrados diario/semanal/mensual (T76). |
| `observability.tf` | Synthetic checks por minuto y alertas (T77). |
| `cloudflare.tf` | TLS 1.3 only, HSTS, WAF gestionado, rate limit de borde, DNS (T73). |

## Uso

```sh
cd infra/terraform
terraform init
terraform plan  -var-file=terraform.tfvars
terraform apply -var-file=terraform.tfvars
```

- `cloudflare_api_token`: `export TF_VAR_cloudflare_api_token=...` (nunca en el repo).
- El **estado** puede contener valores sensibles: bucket GCS cifrado y con IAM restringido.
- Tras `apply`, inyectar los secretos que no se derivan de recursos (p. ej.
  `jwt-signing-key`, `webhook-secret`, KEK/DEK) con el procedimiento de
  [`../auth/`](../auth/README.md) y [`../backup/`](../backup/README.md).

## Rotación de `JWT_SIGNING_KEY` (90 días, solape)

La rotación se ejecuta fuera de Terraform para no reescribir el secreto en el
estado: ver `../auth/rotate-jwt-signing-key.sh` (genera la clave nueva, la
publica con solape de validación y retira la antigua tras la ventana).
