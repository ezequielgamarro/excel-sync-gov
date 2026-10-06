# Historia de incidentes — producción (T77)

Registro append-only de incidentes y de los **ensayos** de continuidad
(failover y restauración). Cada entrada incluye fecha, severidad, impacto,
causa raíz, acciones y enlaces a métricas/alertas. No se incluye PII ni
secretos.

## Plantilla

| Campo | Contenido |
|-------|-----------|
| ID | `INC-YYYY-NNN` |
| Detección | Alerta / synthetic check / reporte |
| Inicio–Fin (UTC) | … |
| Severidad | SEV1 (caída) · SEV2 (degradado) · SEV3 (menor) |
| Impacto | Qué dejó de funcionar y a quién |
| Causa raíz | Análisis (5 porqués) |
| Mitigación | Qué se hizo para recuperar |
| Acciones preventivas | Tareas con responsable y fecha |
| Trazabilidad | `correlation_id`, paneles Grafana, alertas Prometheus |

## Ensayos de continuidad

| Fecha | Tipo | Resultado | Evidencia |
|-------|------|-----------|-----------|
| _pendiente_ | Failover de PostgreSQL (RNF-06.d) | — | [`failover-drill.md`](failover-drill.md) |
| _pendiente_ | Restauración de backup trimestral (RNF-14.d) | — | [`../backup/README.md`](../backup/README.md) |
| _pendiente_ | Reconstrucción de Redis (descartable) | — | — |

> Toda actualización de este registro debe enlazar la evidencia objetiva
> (dashboard, consulta de métricas o salida del ensayo).
