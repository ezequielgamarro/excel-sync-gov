/**
 * CREDENTIALS-001 — Custodia del secreto en `Script Properties` (F6, T42, §9).
 *
 * El secreto del webhook NUNCA se escribe en el código `.gs`/`appsscript.json`
 * (§9.4, AM-14): vive en las propiedades del script (cifrado en reposo por
 * Google). `configureWebhookCredentials` provisiona la versión vigente y
 * conserva la anterior durante la ventana de solape de 24 h (§9.3): el backend
 * acepta ambos `key_id` en ese periodo.
 */

/** Devuelve el almacén de propiedades del script. */
function scriptProps_() {
  return PropertiesService.getScriptProperties();
}

/**
 * Provisiona/rota las credenciales del webhook en `Script Properties`.
 *
 * Solo el `platform-admin` ejecuta esta función desde el editor (o desde el
 * panel interno), tras recibir el secreto **una única vez** desde el backend
 * (§10.1). No registra ni devuelve el material del secreto.
 */
function configureWebhookCredentials(webhookId, docId, keyId, secret, endpoint, allowedHosts) {
  if (!webhookId || !docId || !keyId || !secret) {
    throw new Error('configureWebhookCredentials: faltan webhookId/docId/keyId/secret.');
  }
  var endpointError = validateEndpoint_(endpoint, allowedHosts);
  if (endpointError) {
    throw new Error('configureWebhookCredentials: endpoint inválido — ' + endpointError);
  }
  var props = scriptProps_();
  var previousKey = props.getProperty(CONFIG.PROPS.keyId);
  var previousSecret = props.getProperty(CONFIG.PROPS.secret);
  // Si ya había una versión vigente distinta, se promueve a "anterior" con
  // solape de 24 h (rotación sin downtime, §9.3).
  if (previousKey && previousKey !== keyId && previousSecret) {
    props.setProperty(CONFIG.PROPS.keyIdPrevious, previousKey);
    props.setProperty(CONFIG.PROPS.secretPrevious, previousSecret);
    props.setProperty(
      CONFIG.PROPS.overlapUntil,
      isoUtc_(new Date(Date.now() + CONFIG.OVERLAP_HOURS * 3600 * 1000))
    );
  }
  props.setProperties({
    WEBHOOK_ID: String(webhookId),
    WEBHOOK_DOC_ID: String(docId),
    WEBHOOK_KEY_ID: String(keyId),
    WEBHOOK_SECRET: String(secret),
    WEBHOOK_ENDPOINT: String(endpoint),
    ALLOWED_ENDPOINT_HOSTS: String(allowedHosts || ''),
    WEBHOOK_VERSION: CONFIG.SCHEMA_VERSION,
    WEBHOOK_BLOCKED: ''
  });
  logRun_('configure', 'success', {
    webhook_id: String(webhookId),
    key_id: String(keyId),
    doc_id: String(docId)
  });
}

/** Credenciales vigentes (nunca se registran). */
function activeCredentials_() {
  var props = scriptProps_();
  return {
    webhookId: props.getProperty(CONFIG.PROPS.webhookId) || '',
    docId: props.getProperty(CONFIG.PROPS.docId) || '',
    keyId: props.getProperty(CONFIG.PROPS.keyId) || '',
    secret: props.getProperty(CONFIG.PROPS.secret) || '',
    endpoint: props.getProperty(CONFIG.PROPS.endpoint) || '',
    allowedHosts: props.getProperty(CONFIG.PROPS.allowedHosts) || '',
    version: props.getProperty(CONFIG.PROPS.version) || CONFIG.SCHEMA_VERSION
  };
}

/** Versión anterior, solo si sigue dentro de la ventana de solape de 24 h. */
function previousCredentials_() {
  var props = scriptProps_();
  var until = props.getProperty(CONFIG.PROPS.overlapUntil);
  var keyId = props.getProperty(CONFIG.PROPS.keyIdPrevious) || '';
  var secret = props.getProperty(CONFIG.PROPS.secretPrevious) || '';
  if (!keyId || !secret || !until) return null;
  if (new Date(until).getTime() <= Date.now()) return null;
  var active = activeCredentials_();
  return {
    webhookId: active.webhookId,
    docId: active.docId,
    keyId: keyId,
    secret: secret,
    endpoint: active.endpoint,
    allowedHosts: active.allowedHosts,
    version: active.version
  };
}

/**
 * Valida el endpoint de salida contra la allowlist de hosts (P7, §3.4).
 * Devuelve `''` si es válido o un motivo accionable si no lo es.
 */
function validateEndpoint_(endpoint, allowedHosts) {
  if (!endpoint || endpoint.indexOf('https://') !== 0) {
    return 'se exige HTTPS (https://).';
  }
  var host = endpoint.replace(/^https:\/\//, '').split('/')[0].split(':')[0].toLowerCase();
  var allowed = String(allowedHosts || '')
    .split(',')
    .map(function (item) { return item.trim().toLowerCase(); })
    .filter(function (item) { return item !== ''; });
  if (allowed.length === 0) {
    return 'ALLOWED_ENDPOINT_HOSTS no configurada (fail-closed).';
  }
  if (allowed.indexOf(host) < 0) {
    return 'host "' + host + '" fuera de la allowlist.';
  }
  return '';
}

/** ¿Está el webhook suspendido (403: key revocada/no vigente)? */
function isWebhookBlocked_() {
  return scriptProps_().getProperty(CONFIG.PROPS.blocked) === '1';
}
