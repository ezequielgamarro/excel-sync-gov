# Backups y recuperación ante desastres (T76, RNF-14)

Snapshots cifrados, PITR y ensayos de restauración del sistema. La
infraestructura de buckets/KMS está en [`../terraform/backups.tf`](../terraform/backups.tf).

## Objetivos

| Indicador | Valor | Fuente |
|-----------|-------|--------|
| **RPO** | 15 min | PITR de Cloud SQL (WAL continuo) + snapshot diario — RNF-14.a |
| **RTO** | 2 h | restauración snapshot+PITR, reconstruir réplicas y Redis (descartable), reconectar webhook y operadores — RNF-14.b |
| Retención diaria | **35 días** | RNF-14.c |
| Retención semanal | **12 semanas (84 d)** | RNF-14.c |
| Retención mensual | **24 meses (730 d)** | RNF-14.c |
| Cifrado | clave **independiente** de producción | RNF-14.c |
| Almacén | bucket cifrado, **geográficamente separado** | RNF-14.e |
| Verificación | checksum SHA-256 + **ensayo trimestral** | RNF-14.d |

## Contenido del backup

- **PostgreSQL completo** (formato custom): incluye historiales, agregados,
  auditoría append-only, metadatos de webhooks y el **almacén de usuarios
  locales `app.user_account`** (hashes Argon2id) y `app.refresh_token` — RNF-14.f.
- **Dump dirigido** de `app.user_account` + `app.refresh_token` (segunda copia
  verificable del almacén de identidad).
- **Secretos**: los valores (`JWT_SIGNING_KEY`, secreto del webhook, KEK/DEK…)
  residen en Secret Manager, que aplica su propia replicación y protección; el
  ensayo de DR comprueba su recuperabilidad (el material nunca se escribe en
  claro en los snapshots).

## Operación

```sh
# Snapshot diario (programar con Cloud Scheduler: daily/weekly/monthly)
TIER=daily DATABASE_URL=... BACKUP_ENCRYPTION_KEY=... \
  BACKUP_BUCKET_DAILY=... infra/backup/backup.sh

# Ensayo trimestral de restauración (incluye verificación de checksum)
BACKUP_URI=gs://.../daily/20260101T030000Z.enc.bundle \
SCRATCH_DATABASE_URL=... BACKUP_ENCRYPTION_KEY=... \
  infra/backup/verify-restore.sh
```

## Ensayo trimestral (RNF-14.d)

1. Seleccionar el snapshot más reciente de cada tier.
2. `verify-restore.sh`: verifica **checksum**, descifra y restaura en una base
   *scratch*; comprueba `app.user_account`, `app.refresh_token` y
   `audit.audit_event`.
3. Probar la recuperación de un secreto desde Secret Manager (acceso del rol de
   respaldo).
4. Registrar **fecha, responsable y resultado** en el historial de incidentes
   ([`../observability/incident-history.md`](../observability/incident-history.md)).

> La clave de respaldo se rota por ciclo; la clave histórica necesaria para
> restaurar se conserva protegida (nunca en el repositorio).
