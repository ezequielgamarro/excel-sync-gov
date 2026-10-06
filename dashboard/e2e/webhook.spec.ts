/**
 * T67/T70 — flujo E2E del webhook firmado de Apps Script (CA-01.1/01.2/01.3/
 * 01.6/01.7). Simula el payload y la firma HMAC-SHA256 de
 * `apps-script/50_signer.gs` contra el backend real.
 *
 * Requiere `E2E_API_URL` y las credenciales de prueba:
 *   E2E_API_URL, E2E_WEBHOOK_ID, E2E_WEBHOOK_KEY_ID, E2E_WEBHOOK_SECRET (hex).
 * Si faltan, los tests se omiten (no rompen CI sin backend).
 */

import { createHash, createHmac, randomBytes } from "node:crypto";
import { expect, test } from "@playwright/test";
import { makeSnapshot } from "./fixtures";

const API_URL = process.env.E2E_API_URL ?? "";
const WEBHOOK_ID = process.env.E2E_WEBHOOK_ID ?? "";
const KEY_ID = process.env.E2E_WEBHOOK_KEY_ID ?? "";
const SECRET = process.env.E2E_WEBHOOK_SECRET ?? "";
const VERSION = "1.0.0";

test.skip(
  !API_URL || !WEBHOOK_ID || !KEY_ID || !SECRET,
  "Faltan E2E_API_URL / E2E_WEBHOOK_ID / E2E_WEBHOOK_KEY_ID / E2E_WEBHOOK_SECRET",
);

function secretBytes(): Buffer {
  return Buffer.from(SECRET, "hex");
}

function ingestBody(eventId: string): string {
  const snapshot = makeSnapshot(1);
  const payload = snapshot.payload as Record<string, unknown>;
  return JSON.stringify({
    schema_version: VERSION,
    event_id: eventId,
    doc_id: "sifcop-resumen",
    sheet_modified_at: "2026-10-03T14:21:58Z",
    data_date: "2026-10-03",
    tz: "America/Argentina/Buenos_Aires",
    content_sha256: createHash("sha256").update(String(snapshot.event_id)).digest("hex"),
    payload: {
      kpis: payload.kpis,
      regional: payload.regional,
      turnos: payload.turnos,
      ranking: payload.ranking,
    },
  });
}

function canonical(body: string, nonce: string, timestamp: string): string {
  const contentSha = createHash("sha256").update(body).digest("hex");
  return [WEBHOOK_ID, KEY_ID, nonce, timestamp, VERSION, contentSha].join("|");
}

function signedHeaders(body: string, nonce: string, timestamp: string): Record<string, string> {
  const signature = createHmac("sha256", secretBytes()).update(canonical(body, nonce, timestamp)).digest("hex");
  return {
    "Content-Type": "application/json",
    "X-Webhook-Id": WEBHOOK_ID,
    "X-Webhook-Key-Id": KEY_ID,
    "X-Webhook-Nonce": nonce,
    "X-Webhook-Timestamp": timestamp,
    "X-Webhook-Version": VERSION,
    "X-Webhook-Signature": `sha256=${signature}`,
  };
}

test("webhook firmado válido → 202 y el duplicado → 200 duplicate=true", async ({ request }) => {
  const eventId = `e2e-${randomBytes(8).toString("hex")}`;
  const body = ingestBody(eventId);
  const nonce = randomBytes(16).toString("hex");
  const timestamp = new Date().toISOString();

  const accepted = await request.post(`${API_URL}/api/v1/ingest/webhook`, {
    headers: signedHeaders(body, nonce, timestamp),
    data: body,
  });
  expect(accepted.status()).toBe(202);

  const duplicate = await request.post(`${API_URL}/api/v1/ingest/webhook`, {
    headers: signedHeaders(body, randomBytes(16).toString("hex"), new Date().toISOString()),
    data: body,
  });
  expect(duplicate.status()).toBe(200);
  expect((await duplicate.json()).duplicate).toBe(true);
});

test("cuerpo manipulado tras firmar → 401 sin deserializar (CA-01.3)", async ({ request }) => {
  const body = ingestBody(`e2e-${randomBytes(8).toString("hex")}`);
  const headers = signedHeaders(body, randomBytes(16).toString("hex"), new Date().toISOString());
  const tampered = body.replace(/"value":\d+/, '"value":999999');

  const response = await request.post(`${API_URL}/api/v1/ingest/webhook`, { headers, data: tampered });
  expect(response.status()).toBe(401);
});

test("nonce reutilizado (anti-replay) → 409 (CA-01.6)", async ({ request }) => {
  const nonce = randomBytes(16).toString("hex");
  const timestamp = new Date().toISOString();
  const first = ingestBody(`e2e-${randomBytes(8).toString("hex")}`);
  await request.post(`${API_URL}/api/v1/ingest/webhook`, {
    headers: signedHeaders(first, nonce, timestamp),
    data: first,
  });
  const second = ingestBody(`e2e-${randomBytes(8).toString("hex")}`);
  const replay = await request.post(`${API_URL}/api/v1/ingest/webhook`, {
    headers: signedHeaders(second, nonce, timestamp),
    data: second,
  });
  expect(replay.status()).toBe(409);
});

test("sin firma → 401 (CA-01.2)", async ({ request }) => {
  const body = ingestBody(`e2e-${randomBytes(8).toString("hex")}`);
  const headers = signedHeaders(body, randomBytes(16).toString("hex"), new Date().toISOString());
  delete (headers as Record<string, string>)["X-Webhook-Signature"];
  const response = await request.post(`${API_URL}/api/v1/ingest/webhook`, { headers, data: body });
  expect(response.status()).toBe(401);
});
