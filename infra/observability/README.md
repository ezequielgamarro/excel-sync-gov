# Observabilidad de producción (T77, RNF-07)

Stack de métricas, dashboards, alertas y sondeos sintéticos del sistema en
producción.

| Componente | Fichero |
|------------|---------|
| Scraping Prometheus (backend interno + synthetic 1/min) | `prometheus/prometheus.yml` |
| Reglas de alerta (RNF-07.d) | `prometheus/alerts.yml` |
| Datasource Grafana | `grafana/provisioning/datasources/prometheus.yml` |
| Aprovisionamiento de dashboards | `grafana/provisioning/dashboards/dashboards.yml` |
| Dashboard de operación | `grafana/dashboards/excel-sync-gov.json` |
| Sondeos sintéticos por minuto | `synthetic/checks.yaml` · `synthetic/run-synthetic-checks.sh` |
| Uptime checks + alertas gestionadas | `../terraform/observability.tf` |
| Historia de incidentes y ensayos | `incident-history.md` |
| Ensayo de failover | `failover-drill.md` |

## Señales cubiertas (RNF-07.a/f)

- Latencia de ingesta (p50/p95/p99), eventos/s, conexiones WSS activas,
  reconexiones, mensajes rechazados por causa, tasa de polling, tamaño de
  payload y errores 4xx/5xx por endpoint.
- **Synthetic checks por minuto** (≥60 s) de `/health/live`, `/health/ready`,
  cold start `/dashboard/snapshot` y el app shell, con umbral de latencia.
- **Fracción de actualizaciones** que llegan al dashboard agregada por
  `event_id`, expuesta como latencia percibida real (RNF-07.f).

## Alertas (RNF-07.d)

p95 de latencia > 2 s (10 min) · tasa de rechazo > 1 % · WSS a 0 con sala activa
· último webhook > 5 min · payload > 64 KB · debounce SQL > 1 % · backend caído
· synthetic check en rojo. La severidad y el canal se definen por entorno.

## Despliegue

- Prometheus/Grafana corren en la **red interna**; `/metrics` nunca se expone en
  el edge (RNF-07.c). El token del scraper se lee de fichero (nunca en el repo).
- Los dashboards y reglas son **código versionado** (sin configuración manual).
- Los ensayos (failover y restauración) se ejecutan **trimestralmente** y se
  registran en `incident-history.md`.
