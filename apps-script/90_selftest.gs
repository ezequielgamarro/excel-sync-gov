/**
 * SELFTEST-001 — Pruebas de las funciones puras del Apps Script (F6).
 *
 * Se ejecuta desde el editor (`runSelfTests`). No realiza llamadas de red ni
 * escribe en el documento. Verifica hashes, JSON canónico, nonce/UUIDv7,
 * firma, allowlist de cabeceras y validación de endpoint.
 */
function runSelfTests() {
  var failures = [];
  function check(name, condition) {
    if (!condition) failures.push(name);
  }

  check('sha256_abc',
    sha256Hex_('abc') ===
    ('ba7816bf8f01cfea' + '414140de5dae2223b00361a396177a9c' + 'b410ff61f20015ad'));
  check('canonical_stable', canonicalJson_({ b: 1, a: [2, 1] }) === '{"a":[2,1],"b":1}');
  check('nonce_len', newNonce_().length === 32);
  check('uuid_v7_format',
    /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-8[0-9a-f]{3}-[0-9a-f]{12}$/.test(newEventId_()));

  var secret = 'test-secret-not-a-real-key';
  var canonical = 'a|b|c|d|1.0.0|' + sha256Hex_('x');
  var header = computeSignatureHeader_(secret, canonical);
  check('signature_prefix', header.indexOf('sha256=') === 0 && header.length === 71);

  check('headers_ok',
    JSON.stringify(mapHeaders_('kpis', ['kpi_id', 'value'])) ===
    JSON.stringify({ kpi_id: 0, value: 1 }));
  var rejectedUnknown = false;
  try {
    mapHeaders_('kpis', ['kpi_id', 'value', 'columna_rara']);
  } catch (err) {
    rejectedUnknown = true;
  }
  check('headers_reject_unknown', rejectedUnknown);
  var rejectedMissing = false;
  try {
    mapHeaders_('kpis', ['kpi_id', 'label']);
  } catch (err) {
    rejectedMissing = true;
  }
  check('headers_reject_missing', rejectedMissing);

  var jitter = applyJitter_(1000, 0.2);
  check('jitter_bounds', jitter >= 800 && jitter <= 1200);

  check('endpoint_ok', validateEndpoint_('https://api.dominio-gob/x', 'api.dominio-gob') === '');
  check('endpoint_reject_scheme', validateEndpoint_('http://api.dominio-gob/x', 'api.dominio-gob') !== '');
  check('endpoint_reject_host', validateEndpoint_('https://evil.example/x', 'api.dominio-gob') !== '');
  check('endpoint_reject_empty_allowlist', validateEndpoint_('https://api.dominio-gob/x', '') !== '');

  if (failures.length > 0) {
    console.error('self-test FAILED: ' + failures.join(', '));
    throw new Error('Apps Script self-test failed: ' + failures.join(', '));
  }
  console.log('self-test OK');
}
