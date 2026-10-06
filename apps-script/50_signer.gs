/**
 * SIGNER-001 — Firma HMAC-SHA256 + nonce + timestamp (F6, T41, §9.2).
 *
 * Cadena canónica **exacta** (spec §9.2):
 *
 *   HMAC-SHA256(secreto, "{webhook_id}|{key_id}|{nonce}|{timestamp}|{schema_version}|{sha256(cuerpo)}")
 *   X-Webhook-Signature: sha256=<hex>
 *
 * El `timestamp` es la cadena cruda que viaja en `X-Webhook-Timestamp` (lo que
 * se firma es lo que se envía). El `nonce` es de 128 bits. La clave HMAC es el
 * material del secreto decodificado (el backend entrega 256 bits en hex): se
 * decodifica a bytes para que la firma sea interoperable con `app/services/webhook_signature.py`.
 */

/** Decodifica un secreto hex a bytes; si no es hex válido, usa sus bytes UTF-8. */
function secretKeyBytes_(secret) {
  var value = String(secret || '').trim();
  if (value.length > 0 && value.length % 2 === 0 && /^[0-9a-fA-F]+$/.test(value)) {
    var bytes = [];
    for (var i = 0; i < value.length; i += 2) {
      bytes.push(parseInt(value.substr(i, 2), 16));
    }
    return bytes;
  }
  return value;
}

/** Construye la cadena canónica de la firma (§9.2). */
function buildCanonicalString_(webhookId, keyId, nonce, timestamp, version, body) {
  return [
    String(webhookId),
    String(keyId),
    String(nonce),
    String(timestamp),
    String(version),
    sha256Hex_(body)
  ].join('|');
}

/** Calcula `sha256=<hex>` sobre la cadena canónica con el secreto vigente. */
function computeSignatureHeader_(secret, canonicalString) {
  var signature = Utilities.computeHmacSha256Signature(canonicalString, secretKeyBytes_(secret));
  return 'sha256=' + bytesToHex_(signature);
}

/** Cabeceras del webhook firmado (§2.2.1, §10.1). */
function buildWebhookHeaders_(credentials, nonce, timestamp, body, retriesExhausted) {
  var canonical = buildCanonicalString_(
    credentials.webhookId,
    credentials.keyId,
    nonce,
    timestamp,
    credentials.version,
    body
  );
  var headers = {
    'X-Webhook-Id': credentials.webhookId,
    'X-Webhook-Key-Id': credentials.keyId,
    'X-Webhook-Nonce': nonce,
    'X-Webhook-Timestamp': timestamp,
    'X-Webhook-Version': credentials.version,
    'X-Webhook-Signature': computeSignatureHeader_(credentials.secret, canonical),
    'Content-Type': 'application/json',
    'X-Correlation-Id': 'as-' + newNonce_()
  };
  if (retriesExhausted && retriesExhausted > 0) {
    // Reporte de salud del origen (RF-01.j, T46): el backend lo persiste.
    headers['X-Webhook-Retries-Exhausted'] = String(retriesExhausted);
  }
  return headers;
}
