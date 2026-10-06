# Ensayo de failover (T77, RNF-06.d / RNF-14.b)

Procedimiento y criterios de un ensayo de conmutación controlada de la
infraestructura de producción. Se ejecuta al menos **una vez por trimestre** y
tras cambios mayores. El resultado se registra en
[`incident-history.md`](incident-history.md).

## Objetivos

- Verificar el **failover automático** de PostgreSQL (Cloud SQL `REGIONAL`) con
  RPO ≤ 15 min y RTO ≤ 2 h (RNF-14).
- Verificar que el backend **sin estado** sobrevive la pérdida de una réplica
  (el tráfico lo absorben las ≥3 réplicas y Redis permanece).
- Verificar que **Redis es descartable**: su caída degrada el fan-out a polling
  sin pérdida histórica (RNF-06.e).
- Verificar la continuidad de los **synthetic checks** y las alertas.

## Precondiciones

- Ventana de mantenimiento anunciada (≥48 h; no cuenta para el SLA, OD-10).
- Réplicas del backend healthy (≥3) y `wss_connections > 0` en la sala.
- Backup reciente verificado (checksum) disponible.

## Pasos

1. **Captura de línea base**: `up`, `wss_connections`, `ingest_events_total/s`,
   latencia p95 y antigüedad de la última edición.
2. **Failover de PostgreSQL**: forzar la conmutación de la instancia primaria a
   la réplica en otra zona (operación de Cloud SQL). Observar errores 5xx y el
   cierre/reconexión de WSS.
3. **Observabilidad de la conmutación**: confirmar que el synthetic `api-readiness`
   vuelve a verde en ≤ RTO y que las alertas siguen emitiendo.
4. **Redis**: reiniciar la instancia; verificar que el cold start (PostgreSQL)
   sigue sirviendo y que los clientes pasan a polling 10 s, reincorporándose al
   WSS al volver Redis.
5. **Rolling deploy de prueba**: desplegar una imagen nueva y comprobar que se
   mantiene `wss_connections > 0` durante la ventana (`order: start-first`).
6. **Cierre**: documentar desviaciones con `correlation_id` y abrir acciones.

## Criterios de éxito

| Criterio | Umbral |
|----------|--------|
| RPO observado | ≤ 15 min |
| RTO observado | ≤ 2 h (típicamente minutos) |
| Dashboard servido durante el failover | Sí (o degradación a polling visible) |
| Pérdida de eventos | 0 (idempotencia `event_id` + reconciliación) |
| Alertas y synthetic checks | Emiten y se recuperan |
