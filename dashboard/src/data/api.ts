/**
 * Cliente REST del dashboard (T50, §10.2/§10.3).
 *
 * - `cache: "no-store"`, `credentials: "omit"` y `Authorization: Bearer` en
 *   memoria: ninguna respuesta con datos se cachea (AM-10, AM-12).
 * - En `401` se renueva con el refresh rotativo una vez antes de fallar.
 */

import { config } from "../config";
import type { ConsultaAggregation, EstadisticasRespuesta, HospitalesEstadisticas } from "../types";
import {
  ensureFreshToken,
  getAccessToken,
  getCsrfToken,
  refreshAccessToken,
} from "../auth/session";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: string,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request(
  path: string,
  init: RequestInit = {},
  retry = true,
  baseUrl: string = config.apiBaseUrl,
): Promise<unknown> {
  const token = await ensureFreshToken();
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json");
  if (token) headers.set("Authorization", `Bearer ${token}`);
  // Anti-CSRF (AM-12, T63): toda mutación reenvía el token ligado a la sesión.
  const method = (init.method ?? "GET").toUpperCase();
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    const csrf = getCsrfToken();
    if (csrf) headers.set("X-CSRF-Token", csrf);
  }
  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers,
    cache: "no-store",
    credentials: "omit",
  });

  if (response.status === 401 && retry) {
    const renewed = await refreshAccessToken();
    if (renewed) return request(path, init, false, baseUrl);
  }
  if (!response.ok) {
    let code = `HTTP_${response.status}`;
    let message = response.statusText;
    try {
      const body = (await response.json()) as { error?: { code?: string; message?: string } };
      if (body.error?.code) code = body.error.code;
      if (body.error?.message) message = body.error.message;
    } catch {
      /* cuerpo no JSON */
    }
    throw new ApiError(response.status, code, message);
  }
  if (response.status === 204) return null;
  return response.json();
}

/** Cold start: última instantánea aceptada (p95 ≤ 800 ms, RNF-04.c). */
export async function fetchSnapshot(roomId: string): Promise<unknown> {
  const params = new URLSearchParams({ room_id: roomId });
  return request(`/dashboard/snapshot?${params.toString()}`);
}

export interface ConsultaQuery {
  turno?: string;
  unidad?: string;
  resultado?: string;
  causa?: string;
  rango?: string;
}

/**
 * Agregación real de la hoja «CONSULTAS» (nuevos campos) con los filtros
 * globales (Turno, Unidad Regional, Rango). Alimenta KPIs y gráficos.
 */
export async function fetchConsultas(query: ConsultaQuery): Promise<ConsultaAggregation> {
  const params = new URLSearchParams({ rango: query.rango || "24h" });
  if (query.turno) params.set("turno", query.turno);
  if (query.unidad) params.set("unidad", query.unidad);
  if (query.resultado) params.set("resultado", query.resultado);
  if (query.causa) params.set("causa", query.causa);
  const payload = await request(`/dashboard/consultas?${params.toString()}`);
  return payload as ConsultaAggregation;
}

/**
 * Estadísticas de la planilla de hospitales (F: ingresos hospitalarios).
 *
 * El backend monta este router en la raíz (`/api/hospitales`), fuera de
 * `/api/v1`, por lo que se consulta con `baseUrl` vacío (origen relativo).
 */
export async function fetchHospitalesEstadisticas(): Promise<HospitalesEstadisticas> {
  const payload = await request("/api/hospitales/estadisticas", {}, true, "");
  return payload as HospitalesEstadisticas;
}

/**
 * Estadísticas de la hoja `DASHBOARD_WEB` (regionales, dependencias y
 * resultados). El backend monta este router en la raíz (`/api/estadisticas`),
 * fuera de `/api/v1`, por lo que se consulta con `baseUrl` vacío (origen
 * relativo), igual que `fetchHospitalesEstadisticas`.
 */
export async function fetchEstadisticas(rango?: string): Promise<EstadisticasRespuesta> {
  const query = rango ? `?rango=${encodeURIComponent(rango)}` : "";
  const payload = await request(`/api/estadisticas${query}`, {}, true, "");
  return payload as EstadisticasRespuesta;
}

export interface WsTicket {
  ticket: string;
  expires_in: number;
}

/** Ticket WSS de un solo uso (TTL 60 s, RNF-03.d). */
export async function fetchWsTicket(): Promise<WsTicket> {
  const token = getAccessToken();
  if (!token) throw new ApiError(401, "NO_TOKEN", "Sin token de acceso.");
  const body = await request("/auth/ws-ticket", { method: "POST" });
  return body as WsTicket;
}

export { request as apiRequest, config as apiConfig };
