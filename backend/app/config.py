"""Configuración central del backend desde el entorno (pydantic-settings).

Zero Trust (spec §9.5, RNF-13): toda la configuración sensible (URLs de base de
datos y Redis, secretos) se lee **únicamente** del entorno. Ningún secreto se
hardcodea ni se versiona; ``.env.example`` (raíz y ``backend/.env.example``)
documenta los nombres y ``.env`` (ignorado por git) se usa solo en desarrollo.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración tipada y validada del backend.

    Los nombres de variable de entorno no llevan prefijo y coinciden con
    ``.env.example`` (``case_sensitive=False`` permite mayúsculas/minúsculas).
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Aplicación ----------------------------------------------------------
    app_name: str = "excel-sync-gov-backend"
    environment: str = "development"
    log_level: str = "INFO"
    canonical_timezone: str = "America/Argentina/Buenos_Aires"
    default_room_id: str = "sala-central"

    # --- Base de datos (secreto, rol svc_dashboard) --------------------------
    database_url: str = ""

    # --- Redis (secreto; pub/sub, presencia, rate limit) ----------------------
    redis_url: str = ""

    # --- TLS / HSTS (el TLS lo termina el edge; el app añade cabeceras) -------
    # OD-09/RNF-01.a: SOLO TLS 1.3, sin ventana de compatibilidad para 1.2.
    force_tls: bool = False
    hsts_max_age: int = 31536000
    hsts_include_subdomains: bool = True
    hsts_preload: bool = True

    # --- Terminación TLS 1.3 cuando el backend sirve TLS directo (OD-09) -----
    # Certificado/llave/clave de la llave y CA (rutas inyectadas por el gestor
    # de secretos). El contexto resultante negocia SOLO TLS 1.3
    # (app/core/tls.py); en el edge (Cloudflare/WAF) se configura "1.3 only".
    tls_certfile: str = ""
    tls_keyfile: str = ""
    tls_keyfile_password: str = ""
    tls_ca_certs: str = ""
    # Dirección de escucha del servidor embebido (`python -m app.core.tls`).
    host: str = "0.0.0.0"
    port: int = 8000

    # --- CORS (allowlist exacta, separada por comas) --------------------------
    cors_allow_origins: str = ""
    cors_allow_credentials: bool = True

    # --- Red interna (para /metrics y /health/ready, RNF-07.c) ----------------
    # Lista separada por comas de IPs o CIDRs considerados "red interna".
    internal_networks: str = "127.0.0.1,::1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"
    # IPs/CIDRs de proxies en los que se confía para leer X-Forwarded-For.
    # Vacío = no confiar en XFF (usar la IP directa del socket) → evita spoofing.
    trusted_proxies: str = ""

    # --- Rate limiting (RNF-12, §10.6) ---------------------------------------
    # Límite del webhook del origen (Apps Script, cabecera X-Webhook-Id).
    rate_limit_webhook_per_minute: int = 200
    rate_limit_webhook_burst: int = 20
    rate_limit_operator_per_minute: int = 120
    rate_limit_operator_burst: int = 120
    rate_limit_admin_per_minute: int = 50
    rate_limit_admin_burst: int = 50
    rate_limit_use_redis: bool = True

    # --- Cifrado (envelope encryption, §9.1–§9.3) ----------------------------
    # KEK (clave de envoltura AES-256, hex/base64) desde el secret manager.
    # DEK (clave de datos AES-256) por key_id, hex/base64. `KEY_ID` es el alias
    # de la clave de datos vigente (default cuando no hay mapeo por key_id).
    kek_id: str = ""
    kek_material: str = ""
    data_key: str = ""
    key_id: str = ""

    # --- Webhook de Apps Script (origen Google Sheets, §9.2/§9.3, §10.1) ------
    # El material del secreto vive en el secret manager; el origen lo custodia en
    # las `Script Properties` del script. Nunca se hardcodea ni se versiona.
    webhook_id: str = ""
    webhook_key_id: str = ""
    webhook_secret: str = ""  # secreto compartido HMAC-SHA256 (256 bits)
    webhook_version: str = "1.0.0"
    # Endpoint del origen allowlisted usado por la reconciliación por polling
    # de respaldo ante triggers perdidos (RF-01.i).
    webhook_reconcile_endpoint: str = ""

    # --- Gestor de secretos (referencias, RNF-13.a, §9.5) --------------------
    secret_manager_provider: str = ""
    secret_manager_url: str = ""
    secret_manager_token: str = ""
    secret_manager_path: str = ""

    # --- Anti-replay (§2.2.1, RNF-03.f, §10.1) -------------------------------
    replay_window_seconds: int = 600  # ventana del nonce (cache Redis)
    replay_clock_skew_seconds: int = 300  # desalineación temporal máxima

    # --- Límites de tamaño de payload (RNF-12.f, §10.1) ----------------------
    max_payload_plaintext_bytes: int = 262144  # 256 KB (plano)
    max_payload_compressed_bytes: int = 65536  # 64 KB (comprimido)

    # --- WSS / distribución en tiempo real (F4, §10.3) -----------------------
    ws_ticket_ttl_seconds: int = 60  # vida del ticket de un solo uso (RNF-03.d)
    ws_heartbeat_interval_s: int = 15  # heartbeat/ping de aplicación (RNF-05.b)
    ws_client_timeout_s: int = 45  # cierre 4001 si el cliente calla > 45 s
    ws_max_connections_per_room: int = 50  # RNF-12.d
    ws_max_connections_global: int = 200  # RNF-12.d
    # La clave X.509 del JWKS no aplica; la identidad se valida con el token
    # nativo firmado por este backend (más abajo).

    # --- Auth nativa JWT (F5, §2.2.2, RNF-03.a/b) ----------------------------
    # Login local usuario+contraseña: sin IdP externo ni SSO.
    # ``jwt_signing_key`` (HS256) o clave privada PEM (RS256) se inyecta desde el
    # secret manager; jamás se hardcodea, versiona ni registra en logs (RNF-13).
    jwt_signing_key: str = ""
    jwt_algorithm: str = "HS256"  # HS256 | RS256
    jwt_issuer: str = "excel-sync-gov-backend"
    jwt_audience: str = "dashboard-api"
    jwt_access_token_ttl_seconds: int = 900  # 15 min (RNF-03.b)
    jwt_clock_skew_seconds: int = 60
    # Almacén del refresh rotativo: ``memory`` (proceso) o ``redis`` (distribuido).
    jwt_refresh_store: str = "memory"

    # --- Política de contraseñas y bloqueo por intentos (RNF-03.a/i) ---------
    password_min_length: int = 12
    password_require_complexity: bool = True
    login_max_failures: int = 5
    login_lockout_seconds: int = 900  # bloqueo máximo por cuenta
    login_lockout_base_seconds: int = 60  # backoff progresivo base

    # --- RBAC por capacidad y re-verificación (F5, T37, RNF-03.c/e/h) --------
    rbac_enabled: bool = True
    # Re-verificación periódica de rol/capacidad en el WSS; cierre ≤ 30 s al
    # perder el rol (RNF-03.e).
    wss_reverification_seconds: int = 10
    wss_role_close_seconds: int = 30

    # --- Histórico / export (F4, §10.2, OD-07) -------------------------------
    history_supervisor_max_days: int = 90  # detalle horario del supervisor
    history_auditor_max_days: int = 1826  # 60 meses para el auditor

    # --- Integración Google Sheets: salud y reconciliación (F6, T45/T46) ------
    # Umbral de modo degradado del origen (RF-01.j): 15 min sin webhook.
    source_degraded_threshold_seconds: int = 900
    # Cadencia del monitor de salud del origen (registro de degradación).
    source_health_monitor_seconds: int = 60
    # Job de reconciliación por polling de respaldo (RF-01.i, RNF-06.f).
    reconciliation_enabled: bool = False
    reconciliation_interval_seconds: int = 60
    # Credenciales de la service account de Google (solo lectura, secret manager).
    # Material JSON completo o ruta a fichero; NUNCA se versiona (§9.5).
    google_service_account_json: str = ""
    google_sheets_api_base: str = "https://sheets.googleapis.com/v4"
    # Rango A1 opcional por hoja (si se omite, se usa el nombre de la hoja).
    google_sheets_range_suffix: str = ""

    # --- Observabilidad ------------------------------------------------------
    metrics_enabled: bool = True
    # Superficie mínima (P7): docs/openapi de FastAPI deshabilitados por defecto;
    # el contrato autoritativo vive en contracts/openapi.yaml. Activar solo en dev.
    enable_docs: bool = False

    # --- Trazas distribuidas OpenTelemetry (T59, RNF-07.b) -------------------
    # El `trace_id` se propaga del origen (Apps Script, cabecera
    # `X-Correlation-Id`/W3C `traceparent`) al backend y al cliente. Si el SDK de
    # OpenTelemetry está instalado se exportan spans por OTLP; si no, se propaga
    # el contexto W3C igualmente (degradación sin dependencia dura).
    tracing_enabled: bool = True
    otel_service_name: str = "excel-sync-gov-backend"
    otel_exporter_otlp_endpoint: str = ""
    otel_exporter_insecure: bool = False

    # --- Alertas configurables (T60, RNF-07.d) -------------------------------
    alerts_enabled: bool = True
    alert_window_seconds: int = 600  # ventana de evaluación (10 min)
    alert_latency_p95_seconds: float = 2.0  # p95 de latencia de ingesta
    alert_rejection_rate: float = 0.01  # tasa de rechazo > 1 %
    alert_webhook_stale_seconds: int = 300  # último webhook > 5 min
    alert_payload_max_bytes: int = 65536  # payload > 64 KB
    alert_sql_debounce_rate: float = 0.01  # debounce SQL > 1 %
    alert_wss_zero_room_active: bool = True  # WSS a 0 con sala activa

    # --- Anti-CSRF (T63, AM-12) ----------------------------------------------
    # Token ligado a la sesión (bearer) que el cliente reenvía en las mutaciones.
    # ``csrf_secret`` vacío usa ``jwt_signing_key`` como respaldo; si ambos están
    # vacíos (desarrollo) la defensa queda inactiva.
    csrf_enabled: bool = True
    csrf_secret: str = ""
    csrf_header_name: str = "X-CSRF-Token"
    csrf_cookie_samesite: str = "Strict"

    @property
    def cors_origins(self) -> list[str]:
        """Orígenes CORS permitidos (allowlist exacta), normalizados a lista."""
        return [origin.strip() for origin in self.cors_allow_origins.split(",") if origin.strip()]

    @property
    def cors_effective_allow_credentials(self) -> bool:
        """``allow_credentials`` solo es válido con allowlist no vacía (§2.2.2, T18).

        Con la allowlist vacía (deny-all) no se habilita el intercambio de
        credenciales; nunca se combina ``allow_credentials`` con comodín.
        """
        return self.cors_allow_credentials and bool(self.cors_origins)

    @property
    def internal_networks_list(self) -> list[str]:
        """Redes internas como lista de cadenas (IPs o CIDRs)."""
        return [net.strip() for net in self.internal_networks.split(",") if net.strip()]

    @property
    def trusted_proxies_list(self) -> list[str]:
        """Proxies de confianza como lista de cadenas (IPs o CIDRs)."""
        return [proxy.strip() for proxy in self.trusted_proxies.split(",") if proxy.strip()]

    @property
    def hsts_value(self) -> str:
        """Valor de la cabecera ``Strict-Transport-Security`` (RNF-01.b)."""
        parts = [f"max-age={self.hsts_max_age}"]
        if self.hsts_include_subdomains:
            parts.append("includeSubDomains")
        if self.hsts_preload:
            parts.append("preload")
        return "; ".join(parts)


@lru_cache
def get_settings() -> Settings:
    """Devuelve una instancia única (cacheada) de la configuración."""
    return Settings()
