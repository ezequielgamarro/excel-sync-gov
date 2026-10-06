/**
 * HEALTH-001 — Salud y modo degradado del origen (F6, T46; RF-01.i/j).
 *
 * Registra cada ejecución en el log de Apps Script (sin PII ni secretos),
 * persiste el estado del canal (último hash enviado, último evento, reintentos
 * agotados, envío pendiente) y expone un reporte de salud local. El backend
 * refuerza el modo degradado (>15 min sin webhook) y la reconciliación por
 * polling (T45/T46).
 */

/** Log de ejecución estructurado (sin secretos ni PII, RNF-08.c/T64). */
function logRun_(trigger, result, fields) {
  // Denylist anti-fuga: nunca se registra material secreto ni contenido crudo
  // (payloads, celdas, cuerpos) aunque un llamador pase la clave por error.
  var denied = [
    'secret', 'password', 'passwd', 'token', 'payload', 'authorization',
    'cookie', 'private', 'body', 'cell', 'celda', 'raw'
  ];
  var entry = {
    event: 'apps_script.run',
    trigger: String(trigger || 'unknown'),
    result: String(result || 'unknown'),
    ts: isoUtc_(new Date())
  };
  if (fields) {
    Object.keys(fields).forEach(function (key) {
      var lowered = String(key).toLowerCase();
      var blocked = denied.some(function (token) { return lowered.indexOf(token) !== -1; });
      if (blocked) return;
      if (fields[key] !== undefined && fields[key] !== null) entry[key] = fields[key];
    });
  }
  console.log(JSON.stringify(entry));
}

/** Marca un envío exitoso: persiste el hash (dedup T40) y limpia pendientes. */
function markSendSuccess_(contentHash, eventId, sentAt) {
  var props = scriptProps_();
  props.setProperties({
    LAST_SUCCESS_HASH: contentHash,
    LAST_SUCCESS_AT: isoUtc_(sentAt || new Date()),
    LAST_SENT_EVENT_ID: String(eventId || ''),
    PENDING_SEND: '',
    RETRIES_EXHAUSTED: '0',
    LAST_ERROR: '',
    LAST_LOCAL_RECEIVED_AT: isoUtc_(sentAt || new Date())
  });
}

/** Marca un fallo de envío (mantiene el hash para reintentar; no descarta datos). */
function markSendFailure_(reason) {
  var props = scriptProps_();
  props.setProperty(CONFIG.PROPS.lastError, String(reason || 'unknown').slice(0, 200));
  props.setProperty(CONFIG.PROPS.pending, '1');
}

/** Incrementa el contador de reintentos agotados (reportado al backend, T46). */
function bumpRetriesExhausted_() {
  var props = scriptProps_();
  var current = parseInt(props.getProperty(CONFIG.PROPS.retriesExhausted) || '0', 10);
  props.setProperty(CONFIG.PROPS.retriesExhausted, String((isNaN(current) ? 0 : current) + 1));
}

/** Reintentos agotados acumulados desde el último éxito. */
function getRetriesExhausted_() {
  var value = parseInt(scriptProps_().getProperty(CONFIG.PROPS.retriesExhausted) || '0', 10);
  return isNaN(value) ? 0 : value;
}

/** Marca que hay un envío pendiente (se reintenta con el trigger temporal). */
function setPending_() {
  scriptProps_().setProperty(CONFIG.PROPS.pending, '1');
}

/** ¿Hay un envío pendiente de reintento? */
function hasPending_() {
  return scriptProps_().getProperty(CONFIG.PROPS.pending) === '1';
}

/** Reporte de salud local del origen (se puede registrar o exponer por el editor). */
function sourceHealthReport() {
  var props = scriptProps_();
  return {
    webhook_id: props.getProperty(CONFIG.PROPS.webhookId) || '',
    doc_id: props.getProperty(CONFIG.PROPS.docId) || '',
    key_id: props.getProperty(CONFIG.PROPS.keyId) || '',
    last_success_at: props.getProperty(CONFIG.PROPS.lastSentAt) || null,
    last_success_hash: props.getProperty(CONFIG.PROPS.lastHash) || null,
    last_event_id: props.getProperty(CONFIG.PROPS.lastEventId) || null,
    retries_exhausted: getRetriesExhausted_(),
    pending_send: hasPending_(),
    blocked: isWebhookBlocked_(),
    last_error: props.getProperty(CONFIG.PROPS.lastError) || null
  };
}
