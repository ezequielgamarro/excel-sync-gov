# Infraestructura (Infra)

Contiene la **infraestructura como código** (IaC) y la definición de despliegue del sistema: contenedores, topología multi-réplica, red, secretos, borde (Cloudflare), CI/CD, respaldo/DR y observabilidad.

**Stack:** Docker (backend y servicios) · Terraform (PostgreSQL gestionado, Redis, Secret Manager, Google Sheets, Cloudflare) · Cloudflare (Pages, WAF, TLS 1.3) · Prometheus/Grafana · CI/CD.

La **autenticación es nativa** (usuario+contraseña → JWT): no hay componente de identidad externo; ver [`auth/README.md`](auth/README.md).

## Contenido (Fase F10)

| Directorio | Contenido | Tareas |
|------------|-----------|--------|
| [`docker/`](docker/README.md) | Imagen del backend (`backend/Dockerfile`), compose local y stack de producción con **≥3 réplicas** y rolling deploy `start-first`; `rollout.sh`. | T72 |
| [`cloudflare/`](cloudflare/README.md) | Deploy de la SPA en **Cloudflare Pages**, WAF gestionado, rate limit de borde y **TLS 1.3**; la política ejecutable está en `terraform/cloudflare.tf`. | T73 |
| [`terraform/`](terraform/README.md) | IaC: **PostgreSQL gestionado** (PITR/failover), **Redis**, **Secret Manager** (`JWT_SIGNING_KEY`, secreto del webhook), service account de Google Sheets y **borde Cloudflare**. | T73/T74 |
| [`auth/`](auth/README.md) | Auth nativa en despliegue: backup del almacén local y **rotación de `JWT_SIGNING_KEY`** con solape (`rotate-jwt-signing-key.sh`). | T74 |
| [`ci/`](ci/README.md) | CI/CD escalonado: build → test → secret scan → deploy SPA antes que backend → health gate; `health-gate.sh`. | T75 |
| [`backup/`](backup/README.md) | Backups cifrados (35 d / 12 sem / 24 m) con clave separada, verificación de checksum y ensayo trimestral de restauración. | T76 |
| [`observability/`](observability/README.md) | Prometheus/Grafana, **synthetic checks por minuto**, alertas, historia de incidentes y ensayo de failover. | T77 |

## Principios

- **Sin secretos en el repositorio**: solo plantillas de nombres (`.env.example`) y referencias al gestor de secretos (RNF-13).
- **Sin estado en el servidor**: el estado compartido vive en Redis; el backend escala horizontal (RNF-06.c).
- **TLS 1.3 en el borde** (TLS 1.2 deshabilitado) y `sslmode=verify-full` hacia PostgreSQL (RNF-01).
- **RPO 15 min / RTO 2 h** con PITR, failover y ensayos documentados (RNF-14).
