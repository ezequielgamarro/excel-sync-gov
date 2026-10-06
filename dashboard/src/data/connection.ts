/**
 * Gestor del canal en tiempo real del dashboard (T50, RNF-05).
 *
 * - Cold start REST al arrancar y antes de reanudar en vivo tras reconectar.
 * - WSS con ticket de un solo uso; heartbeat de aplicación cada 15 s; watchdog
 *   que cierra si no hay actividad del servidor en 45 s.
 * - Reconexión con backoff 1→30 s y jitter ±20 %.
 * - Si el WSS no se establece en 60 s → degradación a polling cada 10 s.
 */

import { config } from "../config";
import { ApiError, fetchSnapshot, fetchWsTicket } from "./api";
import { backoffDelayMs } from "./backoff";
import { ensureFreshToken, refreshAccessToken } from "../auth/session";
import type { ConnectionPhase } from "../state/dashboardReducer";

const HEARTBEAT_INTERVAL_MS = 15_000;
const CLIENT_TIMEOUT_MS = 45_000;
const WATCHDOG_INTERVAL_MS = 5_000;
const DEGRADE_AFTER_MS = 60_000;
const POLL_INTERVAL_MS = 10_000;

export interface ConnectionHandlers {
  onSnapshot(raw: unknown, coldStart: boolean): void;
  onPhase(phase: ConnectionPhase, attempt: number, degraded: boolean): void;
  onDenied(): void;
  /** El servidor confirma sesión viva (hello/heartbeat): marca de sincronización. */
  onHeartbeat?(): void;
}

export class DashboardConnection {
  private ws: WebSocket | null = null;
  private stopped = true;
  private attempt = 0;
  private live = false;
  private degraded = false;
  private polling = false;
  private lastServerActivity = 0;

  private reconnectTimer: number | null = null;
  private pollTimer: number | null = null;
  private pingTimer: number | null = null;
  private watchdogTimer: number | null = null;
  private degradeTimer: number | null = null;

  constructor(
    private readonly handlers: ConnectionHandlers,
    private readonly roomId: string = config.roomId,
  ) {}

  start(): void {
    if (!this.stopped) return;
    this.stopped = false;
    this.attempt = 0;
    void this.bootstrap();
  }

  stop(): void {
    this.stopped = true;
    this.clearTimers();
    this.closeSocket();
    this.live = false;
    this.degraded = false;
  }

  /** Fuerza un cold start (p. ej. tras un hueco `Δseq > 50`, RNF-11.c). */
  async requestColdStart(): Promise<void> {
    await this.coldStart();
  }

  private clearTimers(): void {
    for (const timer of [
      this.reconnectTimer,
      this.pollTimer,
      this.pingTimer,
      this.watchdogTimer,
      this.degradeTimer,
    ]) {
      if (timer !== null) window.clearTimeout(timer);
      if (timer !== null) window.clearInterval(timer);
    }
    this.reconnectTimer = null;
    this.pollTimer = null;
    this.pingTimer = null;
    this.watchdogTimer = null;
    this.degradeTimer = null;
  }

  private closeSocket(): void {
    if (this.ws) {
      this.ws.onopen = null;
      this.ws.onmessage = null;
      this.ws.onerror = null;
      this.ws.onclose = null;
      try {
        this.ws.close(1000, "client-stop");
      } catch {
        /* ya cerrado */
      }
      this.ws = null;
    }
  }

  private async bootstrap(): Promise<void> {
    await this.coldStart();
    if (this.stopped) return;
    await this.openSocket();
  }

  private async coldStart(): Promise<void> {
    try {
      const raw = await fetchSnapshot(this.roomId);
      this.handlers.onSnapshot(raw, true);
    } catch (error) {
      if (error instanceof ApiError && error.status === 403) {
        this.handlers.onDenied();
        this.stop();
      }
      // 401/503/409: se continúa; el WSS o el polling reintentarán.
    }
  }

  private async openSocket(): Promise<void> {
    if (this.stopped) return;
    this.armDegradeTimer();

    let ticket: { ticket: string };
    try {
      await ensureFreshToken();
      ticket = await fetchWsTicket();
    } catch (error) {
      if (error instanceof ApiError && error.status === 403) {
        this.handlers.onDenied();
        this.stop();
        return;
      }
      this.scheduleReconnect(false);
      return;
    }
    if (this.stopped) return;

    let socket: WebSocket;
    try {
      const url = `${config.wsUrl}?ticket=${encodeURIComponent(ticket.ticket)}`;
      socket = new WebSocket(url);
    } catch {
      this.scheduleReconnect(false);
      return;
    }

    this.ws = socket;
    socket.onopen = () => {
      void this.handleOpen();
    };
    socket.onmessage = (event) => this.handleMessage(event);
    socket.onerror = () => {
      /* el cierre se gestiona en onclose */
    };
    socket.onclose = (event) => this.handleClose(event.code);
  }

  private async handleOpen(): Promise<void> {
    if (this.stopped) return;
    this.attempt = 0;
    this.lastServerActivity = Date.now();
    this.degraded = false;
    this.clearDegradeTimer();
    this.stopPolling();

    // Cerrar polling y pedir cold start antes de reanudar en vivo (RNF-05.e).
    await this.coldStart();

    if (this.stopped || !this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    this.live = true;
    this.startPing();
    this.startWatchdog();
    this.handlers.onPhase("live", 0, false);
  }

  private handleMessage(event: MessageEvent): void {
    this.lastServerActivity = Date.now();
    let raw: unknown;
    try {
      raw = JSON.parse(String(event.data));
    } catch {
      return; // mensaje no JSON: se ignora (fail-closed no aplica a ruido)
    }
    if (typeof raw !== "object" || raw === null) return;
    const type = (raw as { type?: unknown }).type;
    if (type === "hello") {
      this.attempt = 0;
      this.handlers.onHeartbeat?.();
      if (!this.live) {
        this.live = true;
        this.startPing();
        this.startWatchdog();
        this.handlers.onPhase("live", 0, false);
      }
      return;
    }
    if (type === "indicators.snapshot") {
      this.handlers.onSnapshot(raw, false);
      return;
    }
    // `heartbeat` confirma que la sesión sigue sincronizada.
    if (type === "heartbeat") {
      this.handlers.onHeartbeat?.();
      return;
    }
    // `error` u otros solo actualizan actividad.
  }

  private handleClose(code: number): void {
    this.cleanupAfterClose();
    if (this.stopped) return;

    if (code === 4003) {
      // Capacidad revocada / no autorizado (AM-01).
      this.handlers.onDenied();
      this.stop();
      return;
    }
    if (code === 4401 || code === 4403) {
      // Ticket inválido o rol cambiado: re-autenticar y reintentar (backoff).
      void refreshAccessToken().finally(() => this.scheduleReconnect(false));
      return;
    }
    // Cierre anómalo de red → reintento inmediato en el primer intento.
    const immediate = (code === 1006 || code === 4001) && this.attempt === 0;
    this.scheduleReconnect(immediate);
  }

  private cleanupAfterClose(): void {
    this.live = false;
    this.clearPing();
    this.clearWatchdog();
    if (this.ws) {
      this.ws.onopen = null;
      this.ws.onmessage = null;
      this.ws.onerror = null;
      this.ws.onclose = null;
      this.ws = null;
    }
  }

  private scheduleReconnect(immediate: boolean): void {
    if (this.stopped) return;
    if (this.reconnectTimer !== null) return;
    this.attempt += 1;
    const delay = immediate ? 0 : backoffDelayMs(this.attempt);
    this.handlers.onPhase("reconnecting", this.attempt, this.degraded);
    this.reconnectTimer = window.setTimeout(() => {
      this.reconnectTimer = null;
      void this.openSocket();
    }, delay);
  }

  private armDegradeTimer(): void {
    this.clearDegradeTimer();
    this.degradeTimer = window.setTimeout(() => {
      if (this.stopped || this.live) return;
      this.startPolling();
    }, DEGRADE_AFTER_MS);
  }

  private clearDegradeTimer(): void {
    if (this.degradeTimer !== null) {
      window.clearTimeout(this.degradeTimer);
      this.degradeTimer = null;
    }
  }

  private startPolling(): void {
    if (this.polling || this.stopped || this.live) return;
    this.polling = true;
    this.degraded = true;
    this.handlers.onPhase("degraded", this.attempt, true);
    const poll = () => {
      void this.coldStart();
    };
    poll();
    this.pollTimer = window.setInterval(poll, POLL_INTERVAL_MS);
  }

  private stopPolling(): void {
    if (this.pollTimer !== null) {
      window.clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
    this.polling = false;
  }

  private startPing(): void {
    this.clearPing();
    this.pingTimer = window.setInterval(() => {
      if (this.ws && this.ws.readyState === WebSocket.OPEN) {
        try {
          this.ws.send(JSON.stringify({ type: "ping", t: Date.now() }));
        } catch {
          /* el watchdog reconectará */
        }
      }
    }, HEARTBEAT_INTERVAL_MS);
  }

  private clearPing(): void {
    if (this.pingTimer !== null) {
      window.clearInterval(this.pingTimer);
      this.pingTimer = null;
    }
  }

  private startWatchdog(): void {
    this.clearWatchdog();
    this.watchdogTimer = window.setInterval(() => {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
      if (Date.now() - this.lastServerActivity > CLIENT_TIMEOUT_MS) {
        // Sin actividad del servidor en 45 s → cerrar y reconectar (RNF-05.b).
        try {
          this.ws.close(4001, "heartbeat-timeout");
        } catch {
          /* ignorar */
        }
      }
    }, WATCHDOG_INTERVAL_MS);
  }

  private clearWatchdog(): void {
    if (this.watchdogTimer !== null) {
      window.clearInterval(this.watchdogTimer);
      this.watchdogTimer = null;
    }
  }
}
