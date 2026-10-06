"""Servicios de negocio del backend (F3: ingesta segura; F4: distribución en vivo).

Módulos F3 (T22–T27):

- ``webhook_signature`` — verificación HMAC-SHA256 del webhook + resolución del
  secreto por ``key_id`` vigente (secret manager, solape 24 h) (T22).
- ``auth`` — autenticación del webhook (cadena de verificación, T23).
- ``replay`` — anti-replay (nonce + ventana temporal) (T24).
- ``validation`` — validación de esquema/rangos/catálogos (T25).
- ``db`` — capa de persistencia asíncrona (SQLAlchemy async).
- ``audit`` — auditoría append-only.
- ``ingest`` — persistencia idempotente de la ingesta (T26).
- ``agents`` — provisión/rotación del secreto del webhook (T27; migrado del
  flujo retirado de activación de agentes).

Módulos F4 (T28–T33):

- ``bus`` — Redis pub/sub fan-out por sala + ``seq`` (T28).
- ``aggregate`` — variación "vs ayer" + formato es-CL (T33).
- ``capacity`` — capacidades/identidad del operador (hook F5).
- ``ticket`` — ticket WSS de un solo uso (T29).

Módulos F6 (T38–T46, integración Google Sheets):

- ``source_health`` — salud del origen (última recepción, reintentos agotados,
  modo degradado > 15 min) y reporte para ``GET /admin/webhook`` (T46).
- ``reconciliation`` — reconciliación por polling de respaldo con service account
  de Google Sheets de solo lectura + supervisor programado (T45).
"""
