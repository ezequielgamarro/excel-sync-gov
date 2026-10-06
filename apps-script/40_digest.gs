/**
 * DIGEST-001 — Hash de contenido y deduplicación (F6, T40, RF-01.c).
 *
 * El `content_sha256` es el SHA-256 del **contenido normalizado** de las hojas
 * vigiladas: la rejilla cruda (valores de pantalla) serializada con JSON
 * canónico (claves ordenadas) más `schema_version` y `data_date`. Al ser todo
 * cadenas, el hash es estable e idéntico al que calcula la reconciliación del
 * backend (T45, `Sheets API FORMATTED_VALUE`). Si coincide con el último hash
 * enviado con éxito, no se envía nada (deduplicación por contenido, AM-08).
 */

/** Hash SHA-256 (hex) del contenido normalizado (rejilla + versión + fecha). */
function contentSha256_(grid, dataDate, version) {
  return sha256Hex_(canonicalJson_({
    schema_version: version || CONFIG.SCHEMA_VERSION,
    data_date: dataDate,
    grid: grid
  }));
}

/**
 * Construye el cuerpo lógico de ingesta (§10.1) listo para firmar y enviar.
 * Devuelve también la representación JSON exacta cuyo SHA-256 se firma.
 */
function buildIngestDocument_() {
  var credentials = activeCredentials_();
  if (!credentials.webhookId || !credentials.docId || !credentials.keyId || !credentials.secret) {
    throw new Error(
      'Credenciales no configuradas: ejecute configureWebhookCredentials(...) ' +
      'con el secreto emitido por el backend (Script Properties, T42).'
    );
  }
  var content = readNormalizedContent_();
  var dataDate = canonicalDate_(new Date());
  var contentHash = contentSha256_(content.grid, dataDate, credentials.version);
  var document = {
    schema_version: credentials.version,
    type: 'indicators.snapshot',
    event_id: newEventId_(),
    doc_id: credentials.docId,
    sheet_modified_at: isoUtc_(new Date()),
    data_date: dataDate,
    tz: CONFIG.TZ,
    content_sha256: contentHash,
    payload: content.payload
  };
  return {
    document: document,
    contentSha256: contentHash,
    body: JSON.stringify(document)
  };
}

/** ¿El contenido normalizado difiere del último enviado con éxito? (T40). */
function hasContentChanged_(contentHash) {
  var last = scriptProps_().getProperty(CONFIG.PROPS.lastHash) || '';
  return last !== contentHash;
}
