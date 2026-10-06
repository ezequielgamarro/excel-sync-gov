/**
 * Configuración NO secreta del cliente (T47/T49, §2.2.5, RNF-13.b).
 *
 * Solo el origen público de la API. No hay secretos en el bundle (la auth es
 * nativa: usuario+contraseña contra el backend).
 */

function trimTrailingSlash(value: string): string {
  return value.replace(/\/+$/, "");
}

function deriveWsUrl(apiBase: string): string {
  try {
    const parsed = new URL(apiBase, window.location.origin);
    parsed.protocol = parsed.protocol === "https:" ? "wss:" : "ws:";
    parsed.pathname = trimTrailingSlash(parsed.pathname) + "/ws/dashboard";
    parsed.search = "";
    parsed.hash = "";
    return parsed.toString();
  } catch {
    return "wss://localhost/ws/dashboard";
  }
}

const API_BASE_URL = trimTrailingSlash(import.meta.env.VITE_API_BASE_URL || "/api/v1");

export interface AppConfig {
  apiBaseUrl: string;
  wsUrl: string;
  roomId: string;
  basePath: string;
}

export function loadConfig(): AppConfig {
  const wsOverride = import.meta.env.VITE_WS_URL || "";
  return {
    apiBaseUrl: API_BASE_URL,
    wsUrl: wsOverride ? trimTrailingSlash(wsOverride) : deriveWsUrl(API_BASE_URL),
    roomId: import.meta.env.VITE_ROOM_ID || "sala-central",
    basePath: import.meta.env.VITE_BASE_PATH || "/",
  };
}

export const config: AppConfig = loadConfig();
