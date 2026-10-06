/**
 * CLIENT-001 — Envío HTTPS con backoff y códigos de estado (F6, T43/T44).
 *
 * `UrlFetchApp` envía a un endpoint **allowlisted** por HTTPS (TLS 1.3 en el
 * borde, §3.4/RNF-01.a), con reintentos y backoff exponencial 2/4/8/16/32/60 s
 * con jitter ±20 % (RF-01.i). Manejo de códigos (§10.1):
 *
 *   - 202/200 → éxito (persiste el hash; dedup T40).
 *   - 401     → alerta y verificación/rotación del secreto (prueba la versión
 *               anterior dentro del solape de 24 h, T42).
 *   - 403     → alerta y **detiene** los envíos hasta verificar (§10.1).
 *   - 409     → regenera nonce y reintenta (el nonce se regenera en cada intento).
 *   - 429     → respeta `Retry-After`.
 *   - 413/422 → alerta; no reintenta el mismo contenido.
 *   - 5xx/red → reintento con backoff.
 *
 * Persiste el último hash y, al agotar reintentos, marca envío pendiente para
 * el trigger temporal y para la reconciliación del backend (RF-01.i, T46).
 * Sin descarte de datos.
 */

/** Punto de entrada de un ciclo: arma el documento y lo entrega (o deduplica). */
function sendCurrentState_(trigger) {
  try {
    if (isWebhookBlocked_()) {
      logRun_(trigger, 'blocked', { reason: 'webhook_blocked_403' });
      return 'blocked';
    }
    var built = buildIngestDocument_();
    var pending = hasPending_();
    if (!hasContentChanged_(built.contentSha256) && !pending) {
      logRun_(trigger, 'noop', { content_sha256: built.contentSha256 });
      return 'noop';
    }
    var credentials = activeCredentials_();
    var endpointError = validateEndpoint_(credentials.endpoint, credentials.allowedHosts);
    if (endpointError) {
      markSendFailure_('invalid_endpoint');
      logRun_(trigger, 'invalid_endpoint', { detail: endpointError });
      return 'invalid_endpoint';
    }
    return deliverWithBackoff_(credentials, built, trigger);
  } catch (err) {
    markSendFailure_(String(err && err.message ? err.message : err).slice(0, 200));
    logRun_(trigger, 'error', { cause: 'exception' });
    return 'error';
  }
}

/** Entrega el documento con reintentos y backoff exponencial + jitter. */
function deliverWithBackoff_(credentials, built, trigger) {
  var lastReason = 'unknown';
  for (var attempt = 0; attempt <= CONFIG.BACKOFF_SECONDS.length; attempt++) {
    var nonce = newNonce_();
    var timestamp = isoUtc_(new Date());
    var headers = buildWebhookHeaders_(
      credentials, nonce, timestamp, built.body, getRetriesExhausted_()
    );
    var response = fetchOnce_(credentials.endpoint, built.body, headers, trigger, attempt, 'current');
    if (response) {
      var code = response.getResponseCode();
      if (code === 202 || code === 200) {
        markSendSuccess_(built.contentSha256, built.document.event_id, new Date());
        logRun_(trigger, 'sent', {
          http_status: code,
          event_id: built.document.event_id,
          content_sha256: built.contentSha256
        });
        return 'sent';
      }
      if (code === 403) {
        // Revocado / key no vigente: detener hasta verificar (§10.1).
        scriptProps_().setProperty(CONFIG.PROPS.blocked, '1');
        markSendFailure_('http_403');
        logRun_(trigger, 'blocked', { http_status: code, cause: 'webhook_revoked_or_key_inactive' });
        return 'blocked';
      }
      if (code === 413 || code === 422) {
        markSendFailure_('http_' + code);
        logRun_(trigger, 'invalid', { http_status: code, cause: 'payload_or_schema' });
        return 'invalid';
      }
      if (code === 401) {
        // Firma inválida: puede ser rotación en curso → probar versión anterior.
        var previous = previousCredentials_();
        if (previous) {
          var previousHeaders = buildWebhookHeaders_(
            previous, newNonce_(), isoUtc_(new Date()), built.body, getRetriesExhausted_()
          );
          var previousResponse = fetchOnce_(
            previous.endpoint, built.body, previousHeaders, trigger, attempt, 'previous'
          );
          if (previousResponse &&
              (previousResponse.getResponseCode() === 202 || previousResponse.getResponseCode() === 200)) {
            markSendSuccess_(built.contentSha256, built.document.event_id, new Date());
            logRun_(trigger, 'sent', { http_status: previousResponse.getResponseCode(), key: 'previous' });
            return 'sent';
          }
        }
        lastReason = 'http_401';
        logRun_(trigger, 'alert', { http_status: code, cause: 'signature_or_secret' });
      } else if (code === 429) {
        // Respeta Retry-After (segundos o fecha HTTP), topado a 60 s.
        var wait = retryAfterMs_(response);
        if (wait !== null) sleepMs_(Math.min(wait, 60000));
        lastReason = 'http_429';
      } else {
        lastReason = 'http_' + code;
      }
    } else {
      lastReason = 'network_error';
    }
    if (attempt < CONFIG.BACKOFF_SECONDS.length) {
      sleepMs_(applyJitter_(CONFIG.BACKOFF_SECONDS[attempt] * 1000));
    }
  }
  bumpRetriesExhausted_();
  setPending_();
  markSendFailure_(lastReason);
  logRun_(trigger, 'failed', {
    cause: lastReason,
    retries_exhausted: getRetriesExhausted()
  });
  return 'failed';
}

/** Realiza un intento HTTP (devuelve `null` ante error de red). */
function fetchOnce_(endpoint, body, headers, trigger, attempt, phase) {
  try {
    return UrlFetchApp.fetch(endpoint, {
      method: 'post',
      contentType: 'application/json',
      payload: body,
      headers: headers,
      muteHttpExceptions: true,
      validateHttpsCertificates: true,
      followRedirects: false
    });
  } catch (err) {
    logRun_(trigger, 'retry', { attempt: attempt + 1, phase: phase, cause: 'network_error' });
    return null;
  }
}

/** Lee `Retry-After` (segundos o fecha HTTP) y lo devuelve en ms (o `null`). */
function retryAfterMs_(response) {
  var headers = response.getAllHeaders();
  var value = headers['Retry-After'] || headers['retry-after'];
  if (!value) return null;
  var seconds = parseInt(value, 10);
  if (!isNaN(seconds)) return seconds * 1000;
  var date = new Date(value);
  if (!isNaN(date.getTime())) return Math.max(0, date.getTime() - Date.now());
  return null;
}

/** Trigger temporal: reintenta si hay un envío pendiente o cambios locales. */
function retryPendingSend() {
  if (isWebhookBlocked_()) {
    logRun_('retry', 'blocked', { reason: 'webhook_blocked_403' });
    return;
  }
  scheduleProcessing_('retry');
}
