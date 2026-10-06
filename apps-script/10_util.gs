/**
 * UTIL-001 — Utilidades puras del Apps Script (F6).
 *
 * Funciones sin efectos secundarios (salvo `sleepMs_`) reutilizadas por el
 * lector, el digest, el firmador y el cliente. Ninguna registra secretos.
 */

/** Convierte un arreglo de bytes en hexadecimal minúsculo. */
function bytesToHex_(bytes) {
  var out = '';
  for (var i = 0; i < bytes.length; i++) {
    var b = bytes[i] & 0xff;
    out += (b < 16 ? '0' : '') + b.toString(16);
  }
  return out;
}

/** SHA-256 en hexadecimal minúsculo de una cadena UTF-8. */
function sha256Hex_(value) {
  var digest = Utilities.computeDigest(
    Utilities.DigestAlgorithm.SHA_256,
    value,
    Utilities.Charset.UTF_8
  );
  return bytesToHex_(digest);
}

/** Nonce de 128 bits (32 hex) generado con dos UUID v4 (entropía del CSPRNG de Google). */
function newNonce_() {
  return (Utilities.getUuid() + Utilities.getUuid()).replace(/-/g, '').slice(0, 32);
}

/**
 * UUIDv7 (RFC 9562): 48 bits de timestamp Unix en ms + versión 7 + variante 10xx
 * + entropía aleatoria. Se usa como `event_id` (clave de idempotencia, §7.2).
 */
function newEventId_() {
  var ts = Date.now();
  var tsHex = ('000000000000' + ts.toString(16)).slice(-12);
  var rand = Utilities.getUuid().replace(/-/g, '');
  // 32 hex aleatorios: se reserva el primer nibble para la versión y el cuarto
  // byte para la variante.
  var r = rand.slice(0, 12) + '7' + rand.slice(12, 15) + '8' + rand.slice(15, 28);
  var hex = tsHex + r; // 12 + 20 = 32 hex
  return (
    hex.slice(0, 8) + '-' + hex.slice(8, 12) + '-' + hex.slice(12, 16) + '-' +
    hex.slice(16, 20) + '-' + hex.slice(20, 32)
  );
}

/** JSON canónico: claves ordenadas recursivamente y sin espacios (hash estable). */
function canonicalJson_(value) {
  if (value === null || typeof value !== 'object') {
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) {
    var parts = value.map(function (item) {
      return canonicalJson_(item);
    });
    return '[' + parts.join(',') + ']';
  }
  var keys = Object.keys(value).sort();
  var fields = keys.map(function (key) {
    return JSON.stringify(key) + ':' + canonicalJson_(value[key]);
  });
  return '{' + fields.join(',') + '}';
}

/** Fecha en la zona canónica con formato `YYYY-MM-DD`. */
function canonicalDate_(date) {
  return Utilities.formatDate(date || new Date(), CONFIG.TZ, 'yyyy-MM-dd');
}

/** Marca ISO-8601 UTC (cabecera `X-Webhook-Timestamp`, §2.2.1). */
function isoUtc_(date) {
  return (date || new Date()).toISOString();
}

/** Minuto del día (0–1439) en la zona canónica. */
function minuteOfDay_(date) {
  return parseInt(Utilities.formatDate(date || new Date(), CONFIG.TZ, 'HH'), 10) * 60 +
    parseInt(Utilities.formatDate(date || new Date(), CONFIG.TZ, 'mm'), 10);
}

/** Aplica jitter ±`ratio` a una base (backoff del RF-01.i). */
function applyJitter_(baseMs, ratio) {
  var factor = 1 + (Math.random() * 2 - 1) * (ratio === undefined ? CONFIG.JITTER_RATIO : ratio);
  return Math.max(0, Math.round(baseMs * factor));
}

/** Espera bloqueante (Apps Script no dispone de timers asíncronos). */
function sleepMs_(ms) {
  Utilities.sleep(Math.max(0, Math.round(ms)));
}

/** Convierte a entero no negativo o devuelve `fallback`. */
function toInt_(value, fallback) {
  if (value === null || value === undefined || value === '') return fallback;
  var n = typeof value === 'number' ? value : parseInt(String(value).replace(/[^\d-]/g, ''), 10);
  if (isNaN(n)) return fallback;
  return Math.max(0, Math.round(n));
}

/** Convierte a número o devuelve `fallback`. */
function toNumber_(value, fallback) {
  if (value === null || value === undefined || value === '') return fallback;
  var n = typeof value === 'number' ? value : parseFloat(String(value).replace(',', '.'));
  return isNaN(n) ? fallback : n;
}

/** Interpreta booleanos de hoja (`si/no/true/false/1/0`). */
function toBool_(value, fallback) {
  if (value === null || value === undefined || value === '') return fallback;
  var text = String(value).trim().toLowerCase();
  if (['true', '1', 'si', 'sí', 'yes', 'y'].indexOf(text) >= 0) return true;
  if (['false', '0', 'no', 'n'].indexOf(text) >= 0) return false;
  return fallback;
}

/** Redondea a 2 decimales (RNF-15.b). */
function round2_(value) {
  return Math.round(value * 100) / 100;
}

/** Dirección de la variación derivada de `delta_abs` (§7.3). */
function directionOf_(deltaAbs) {
  if (deltaAbs > 0) return 'up';
  if (deltaAbs < 0) return 'down';
  return 'flat';
}
