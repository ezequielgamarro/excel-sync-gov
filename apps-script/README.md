# Apps Script (origen Google Sheets)

El **script vinculado al documento de Google Sheets** (SIFCOP) detecta las
ediciones guardadas por los analistas y notifica al backend mediante un
**webhook firmado con HMAC-SHA256**. No hay proceso local, ni ejecutable, ni
cola en disco: todo ocurre en una cuenta Gmail estándar (sin Workspace).

**Stack:** Google Apps Script (`SpreadsheetApp`, `Utilities`, `UrlFetchApp`,
`PropertiesService`) · trigger instalable `onEdit`/`onChange` · HMAC-SHA256
(`Utilities.computeHmacSha256Signature`) · `Script Properties` para el secreto.

Responsabilidades principales:

- Detectar cambios con un **trigger instalable `onEdit`/`onChange`** y
  **coalescer** ráfagas (750 ms), ignorando cambios de formato o estructura que
  no alteran el contenido de los indicadores.
- Leer en **solo lectura** el documento declarado, normalizar los rangos y
  validar las cabeceras contra la allowlist (5 unidades, 3 turnos, 4 KPIs,
  ranking ≤ 5).
- Calcular el **hash SHA-256 del contenido normalizado** y omitir el envío si es
  idéntico al último aceptado (deduplicación por contenido).
- **Firmar** el cuerpo canónico con **HMAC-SHA256** usando el secreto versionado
  (`key_id`) guardado en **`Script Properties`**, e incluir nonce (128 bits) y
  timestamp UTC.
- Enviar por HTTPS a `POST /api/v1/ingest/webhook` con `UrlFetchApp` y
  **reintentos con backoff exponencial** (2 s, 4 s, 8 s, 16 s, 32 s, 60 s tope;
  jitter ±20 %).
- Reportar salud al backend; ante 15 min sin contacto, el backend activa la
  **reconciliación por polling de respaldo**.

Prácticas obligatorias:

- **Nunca** escribe en el documento origen (el sistema es unidireccional).
- **Nunca** abre puertos de escucha; solo realiza salida HTTPS al endpoint
  allowlisted del backend.
- **Nunca** embebe el secreto en el código `.gs` ni en `appsscript.json`: vive
  únicamente en `Script Properties` (cifrado en reposo por Google).
- Solo puede salir a `api.<dominio-gob>:443`; no llama a ningún otro destino.

La rotación del secreto se limita a actualizar `Script Properties` con la nueva
`key_id` publicada por el administrador; el backend acepta el secreto antiguo y
el nuevo durante **24 h** (solape), sin downtime.

## Archivos (T38–T44)

| Archivo | Tarea | Contenido |
|---------|-------|-----------|
| `appsscript.json` | T38–T44 | Manifiesto: timezone canónica, runtime V8 y scopes de **solo lectura** de Sheets + triggers + salida externa. |
| `00_config.gs` | T38–T44 | Constantes: layout 1:1 hojas→series, allowlist de cabeceras, catálogos cerrados, backoff y claves de `Script Properties`. |
| `10_util.gs` | T38–T44 | Utilidades puras: SHA-256, nonce 128 bits, UUIDv7, JSON canónico, jitter. |
| `20_credentials.gs` | T42 | Custodia del secreto en `Script Properties` con solape de 24 h y allowlist de endpoint (fail-closed). |
| `30_reader.gs` | T39 | Lectura en solo lectura + normalización + validación de cabeceras contra allowlist. |
| `40_digest.gs` | T40 | `content_sha256` del contenido normalizado + deduplicación. |
| `50_signer.gs` | T41 | Cadena canónica §9.2, HMAC-SHA256, nonce y timestamp UTC. |
| `60_client.gs` | T43/T44 | `UrlFetchApp` HTTPS con backoff 2/4/8/16/32/60 s + jitter ±20 % y manejo de 401/403/409/429/413/422. |
| `65_trigger.gs` | T38 | Triggers instalables `onEdit`/`onChange` + coalescencia ~750 ms + trigger temporal de reintento. |
| `70_health.gs` | T46 | Log de ejecución, estado del canal y reporte de salud local. |
| `90_selftest.gs` | — | Pruebas de funciones puras (`runSelfTests`). |

## Layout canónico del documento (OD-15)

Mapeo **1:1 hojas→series**. Cada hoja debe tener exactamente las cabeceras de su
allowlist (orden libre); una cabecera desconocida, duplicada o faltante **falla
cerrado** con aviso accionable (no se adivinan columnas, OOS-06).

| Hoja | Serie | Cabeceras obligatorias | Cabeceras opcionales (allowlist) |
|------|-------|------------------------|----------------------------------|
| `Resumen` | 4 KPIs | `kpi_id`, `value` | `label`, `baseline_value`, `delta_abs`, `delta_pct`, `direction`, `comparison`, `as_of`, `has_reference` |
| `Regional` | 5 unidades | `unidad_id`, `intervenciones` | `label`, `variacion_abs`, `variacion_pct`, `rank` |
| `Turnos` | 3 turnos | `turno_id`, `intervenciones` | `inicio_min`, `fin_min`, `label`, `variacion_abs`, `variacion_pct`, `estado` |
| `Ranking` | Top 5 | `puesto`, `dependencia_id`, `comisaria`, `intervenciones` | `variacion_abs`, `variacion_pct`, `puesto_previo` |

- `kpi_id` ∈ {`total_consultas_sifcop`, `personas_capturadas`,
  `vehiculos_secuestrados`, `armas_secuestradas`}.
- `unidad_id` ∈ {`capital`, `sur`, `este`, `oeste`, `norte`}.
- `turno_id` ∈ {`MAÑANA`, `TARDE`, `NOCHE`}.
- El `content_sha256` es `SHA-256(JSON canónico de {schema_version, data_date,
  payload})` (claves ordenadas); la firma HMAC va sobre la cadena canónica §9.2
  con `sha256(cuerpo)` (el JSON exacto enviado).

## Operación

1. `installTriggers()` — instala `onEdit`, `onChange` y el temporal de reintento
   (cada minuto). Idempotente.
2. `configureWebhookCredentials(webhookId, docId, keyId, secret, endpoint,
   allowedHosts)` — guarda el secreto **una única vez** en `Script Properties`
   (nunca en el código) y define la allowlist de hosts del endpoint.
3. `runSelfTests()` — verifica las funciones puras sin tocar la red.
4. `sourceHealthReport()` — estado local (última recepción, reintentos agotados,
   pendiente/bloqueado) sin exponer secretos.

El `content_sha256` no se filtra a logs con material sensible; el trigger
temporal reintenta pendientes y reconcilia por hash al recuperarse (T43/T46).
