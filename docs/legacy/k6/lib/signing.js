// Utilidades compartidas de los escenarios k6 (T69).
// Firma HMAC-SHA256 con la misma cadena canónica que Apps Script (§9.2).

import crypto from "k6/crypto";

export function getEnv(name, fallback) {
  return __ENV[name] || fallback;
}

function toHex(buffer) {
  const bytes = new Uint8Array(buffer);
  let out = "";
  for (let i = 0; i < bytes.length; i += 1) {
    out += bytes[i].toString(16).padStart(2, "0");
  }
  return out;
}

export function hexToBytes(hex) {
  const clean = String(hex || "").trim();
  const bytes = [];
  for (let i = 0; i < clean.length; i += 2) {
    bytes.push(parseInt(clean.substr(i, 2), 16));
  }
  return new Uint8Array(bytes);
}

export function randomHex(byteLength) {
  return toHex(crypto.randomBytes(byteLength));
}

export function sha256Hex(value) {
  return crypto.sha256(value, "hex");
}

export function buildCanonical(webhookId, keyId, nonce, timestamp, version, body) {
  return [webhookId, keyId, nonce, timestamp, version, sha256Hex(body)].join("|");
}

export function webhookHeaders(config, body) {
  const nonce = randomHex(16);
  const timestamp = new Date().toISOString();
  const canonical = buildCanonical(
    config.webhookId,
    config.keyId,
    nonce,
    timestamp,
    config.version,
    body,
  );
  const signature = crypto.hmac("sha256", hexToBytes(config.secret).buffer, canonical, "hex");
  return {
    nonce,
    timestamp,
    headers: {
      "Content-Type": "application/json",
      "X-Webhook-Id": config.webhookId,
      "X-Webhook-Key-Id": config.keyId,
      "X-Webhook-Nonce": nonce,
      "X-Webhook-Timestamp": timestamp,
      "X-Webhook-Version": config.version,
      "X-Webhook-Signature": `sha256=${signature}`,
    },
  };
}

export function randomEventId() {
  return `k6-${randomHex(8)}`;
}

export function ingestBody(eventId, config) {
  return JSON.stringify({
    schema_version: config.version,
    event_id: eventId,
    doc_id: config.docId,
    sheet_modified_at: new Date().toISOString(),
    data_date: "2026-10-03",
    tz: "America/Argentina/Buenos_Aires",
    content_sha256: sha256Hex(eventId),
    payload: {
      kpis: {
        total_consultas_sifcop: { label: "Total Consultas SIFCOP", value: 184732 },
        personas_capturadas: { label: "Personas Capturadas", value: 4128 },
        vehiculos_secuestrados: { label: "Vehículos Secuestrados", value: 37 },
        armas_secuestradas: { label: "Armas Secuestradas", value: 12 },
      },
      regional: [
        { unidad_id: "capital", label: "Capital", intervenciones: 268 },
        { unidad_id: "sur", label: "Sur", intervenciones: 142 },
        { unidad_id: "este", label: "Este", intervenciones: 98 },
        { unidad_id: "oeste", label: "Oeste", intervenciones: 71 },
        { unidad_id: "norte", label: "Norte", intervenciones: 34 },
      ],
      turnos: [
        { turno_id: "MAÑANA", inicio_min: 360, fin_min: 840, label: "MAÑANA (06-14)", intervenciones: 231 },
        { turno_id: "TARDE", inicio_min: 840, fin_min: 1320, label: "TARDE (14-22)", intervenciones: 318 },
        { turno_id: "NOCHE", inicio_min: 1320, fin_min: 360, label: "NOCHE (22-06)", intervenciones: 142 },
      ],
      ranking: {
        top_n: 5,
        dependencias: [
          { puesto: 1, dependencia_id: "com-12", comisaria: "Comisaría 12", intervenciones: 94 },
        ],
      },
    },
  });
}

export const config = {
  version: getEnv("K6_WEBHOOK_VERSION", "1.0.0"),
  docId: getEnv("K6_DOC_ID", "sifcop-resumen"),
  webhookId: getEnv("K6_WEBHOOK_ID", ""),
  keyId: getEnv("K6_WEBHOOK_KEY_ID", ""),
  secret: getEnv("K6_WEBHOOK_SECRET", ""),
  ingestUrl: getEnv("K6_INGEST_URL", "https://api.example.gob/api/v1/ingest/webhook"),
  apiUrl: getEnv("K6_API_URL", "https://api.example.gob/api/v1"),
  wsUrl: getEnv("K6_WS_URL", "wss://api.example.gob/api/v1/ws/dashboard"),
  accessToken: getEnv("K6_ACCESS_TOKEN", ""),
};
