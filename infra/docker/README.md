# Backend en contenedores — réplicas y rolling deploy (T72, RNF-06.c)

Imagen de runtime del backend y despliegue multi-réplica **sin estado**.

| Fichero | Uso |
|---------|-----|
| `../../backend/Dockerfile` | Imagen multi-stage (runtime mínimo, usuario no-root, `HEALTHCHECK` sobre `/health/live`). |
| `../../backend/.dockerignore` | Contexto de build mínimo; excluye `.env`, tests y artefactos. |
| `docker-compose.yml` | Entorno local/pre-prod: backend + PostgreSQL + Redis; `--scale backend=3`. |
| `docker-stack.prod.yml` | Producción (Swarm): `replicas: 3`, `update_config.order: start-first`, `failure_action: rollback`. |
| `rollout.sh` | Rolling deploy + espera de convergencia de réplicas *healthy*. |

## Estado fuera del proceso (sin estado)

El backend **no guarda estado** en el contenedor:

- fan-out, presencia y **rate limit distribuido** → **Redis**;
- datos, agregados, auditoría y usuarios locales → **PostgreSQL**.

Por eso no se declaran volúmenes de datos en el servicio `backend` y la escala
es horizontal: `docker service scale excel-sync-gov_backend=3` (mínimo **3**).

## Rolling deploy sin corte

En Swarm, `deploy.update_config`:

```yaml
order: start-first          # arranca la réplica nueva y la marca healthy...
parallelism: 1
delay: 10s
failure_action: rollback    # ...y solo entonces retira la antigua
```

Con el `HEALTHCHECK` de la imagen, la nueva réplica no recibe tráfico hasta que
`/health/live` responde 200; el dashboard nunca se queda sin backend. Ante fallo,
`rollback` revierte a la revisión anterior.

```sh
BACKEND_IMAGE=registry/excel-sync-gov-backend:$(git rev-parse --short HEAD) \
  infra/docker/rollout.sh
```

## Endurecimiento

- `read_only: true` + `tmpfs /tmp` (FS inmutable).
- `cap_drop: ALL`, `no-new-privileges`.
- Sin secretos en la imagen ni en los ficheros de despliegue: se inyectan en
  runtime desde el gestor de secretos (RNF-13).
- TLS 1.3 lo termina el **edge** (Cloudflare), no el contenedor (ver T73).
