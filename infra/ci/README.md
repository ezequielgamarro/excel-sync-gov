# CI/CD (T75)

Pipeline escalonado y scripts de despliegue.

| Fichero | Rol |
|---------|-----|
| `../../.github/workflows/deploy.yml` | Pipeline: build → test → secret scan → deploy SPA → deploy backend → health gate. |
| `health-gate.sh` | Puerta de salud post-deploy (liveness/readiness). |
| `../docker/rollout.sh` | Rolling deploy `start-first` sin corte (≥3 réplicas). |
| `../cloudflare/deploy.sh` | Publicación de la SPA en Cloudflare Pages. |

## Orden y garantías

1. **build**: imagen del backend (tag = `git SHA`, inmutable) + bundle de la SPA.
2. **test**: `pytest`, `vitest` y la verificación de la **ventana de 2 minors**
   del contrato (`scripts/check_contract_window.py`, §7.8).
3. **secret-scan**: gitleaks bloquea el despliegue ante secretos (RNF-13.d).
4. **deploy-spa**: la SPA se publica **antes** que el backend; el cliente nuevo
   tolera al backend antiguo durante la ventana de 2 minors.
5. **deploy-backend**: rolling deploy `start-first` (sin corte); ante fallo,
   `rollback` automático.
6. **health-gate**: si `/health/live` (y opcionalmente `/health/ready`) no
   convergen, el pipeline falla y el orquestador revierte.

Los secretos viven en el environment `production` de GitHub y se inyectan en
runtime (nunca se escriben en el repositorio).
