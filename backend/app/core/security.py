"""Seguridad base: TLS/HSTS, cabeceras de hardening, CORS e IP interna.

Zero Trust (spec §2.2.5, §8 AM-03/AM-11/AM-12, RNF-01, RNF-12.e):

- **TLS 1.3 obligatorio** (OD-09/RNF-01.a): sin ventana de compatibilidad para
  TLS 1.2. El TLS se termina en el edge (Cloudflare/WAF, configurado "1.3
  only"); cuando el backend sirve TLS directamente, ``app/core/tls.py`` fuerza
  ``minimum_version = maximum_version = TLSv1_3``.
- El backend añade las cabeceras de seguridad (HSTS, X-Frame-Options, CSP,
  Cache-Control, Pragma) y, si ``force_tls`` está activo, redirige
  ``http`` → ``https`` (RNF-01.c).
- ``/metrics`` y ``/health/ready`` solo son accesibles desde **red interna**
  (RNF-07.c); se valida la IP del cliente contra una lista de CIDRs.
- CORS con **allowlist exacta** (desde entorno), ``allow_credentials`` solo con
  allowlist y ``Vary: Origin`` garantizado (``CORSVaryMiddleware``) — §2.2.2.
"""

from __future__ import annotations

import ipaddress
from typing import Final

from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.config import Settings, get_settings
from app.core.errors import raise_http_error

X_FRAME_OPTIONS: Final = "DENY"
X_CONTENT_TYPE_OPTIONS: Final = "nosniff"
REFERRER_POLICY: Final = "no-referrer"
CROSS_ORIGIN_OPENER_POLICY: Final = "same-origin"
CROSS_ORIGIN_RESOURCE_POLICY: Final = "same-origin"
X_PERMITTED_CROSS_DOMAIN_POLICIES: Final = "none"
CACHE_CONTROL_NO_STORE: Final = "no-store, private"
PRAGMA_NO_CACHE: Final = "no-cache"
# CSP base para respuestas de la API (la CSP estricta de la SPA la sirve
# Cloudflare Pages). `frame-ancestors 'none'` es el invariante de AM-11/T18.
CSP_FRAME_ANCESTORS_NONE: Final = "frame-ancestors 'none'"
CSP_BASE: Final = (
    f"default-src 'none'; {CSP_FRAME_ANCESTORS_NONE}; base-uri 'none'; form-action 'none'"
)
# Rutas de la documentación interactiva (Swagger UI / ReDoc) servidas por FastAPI.
DOCS_PATHS: Final = ("/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json")
# CSP permisiva SOLO para las rutas de docs: Swagger UI carga su bundle y sus
# estilos desde `cdn.jsdelivr.net` y usa un `<script>` inline. El resto de la API
# conserva `CSP_BASE` (default-src 'none'). `frame-ancestors 'none'` se mantiene.
CSP_DOCS: Final = (
    "default-src 'self'; "
    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
    "img-src 'self' data: https://fastapi.tiangolo.com; "
    "font-src 'self' data:; "
    "connect-src 'self'; "
    f"{CSP_FRAME_ANCESTORS_NONE}; base-uri 'none'; form-action 'self'"
)


def _parse_ip(value: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address | None:
    try:
        return ipaddress.ip_address(value)
    except ValueError:
        return None


def _ip_in_networks(ip: str, networks: list[str]) -> bool:
    addr = _parse_ip(ip)
    if addr is None:
        return False
    for network in networks:
        try:
            if isinstance(addr, ipaddress.IPv4Address):
                if addr in ipaddress.IPv4Network(network, strict=False):
                    return True
            elif addr in ipaddress.IPv6Network(network, strict=False):
                return True
        except ValueError:
            continue
    return False


def is_internal_ip(ip: str, settings: Settings) -> bool:
    """Devuelve ``True`` si ``ip`` pertenece a alguna de las redes internas configuradas."""
    return _ip_in_networks(ip, settings.internal_networks_list)


def get_client_ip(request: Request, settings: Settings) -> str:
    """Resuelve la IP del cliente (RNF-07.c).

    ``X-Forwarded-For`` **solo** se honra cuando la conexión directa proviene de
    un proxy de confianza (allowlist ``trusted_proxies``); de lo contrario la
    cabecera se ignora y se usa la IP del socket, de modo que un cliente externo
    no puede falsear su origen para alcanzar ``/metrics`` o ``/health/ready``.
    """
    direct_ip = request.client.host if request.client is not None else ""
    if not settings.trusted_proxies_list:
        return direct_ip
    if not _ip_in_networks(direct_ip, settings.trusted_proxies_list):
        return direct_ip
    forwarded = request.headers.get("X-Forwarded-For")
    if not forwarded:
        return direct_ip
    # Primer salto no confiable desde la izquierda (cliente real de la cadena).
    for candidate in (part.strip() for part in forwarded.split(",")):
        if candidate and not _ip_in_networks(candidate, settings.trusted_proxies_list):
            return candidate
    return forwarded.split(",")[0].strip()


def require_internal_network(request: Request) -> None:
    """Rechaza con ``403`` si la IP del cliente no pertenece a la red interna (RNF-07.c)."""
    settings = get_settings()
    client_ip = get_client_ip(request, settings)
    if not is_internal_ip(client_ip, settings):
        raise_http_error("FORBIDDEN", "Endpoint restringido a la red interna.")


class SecurityHeadersMiddleware:
    """Inyecta cabeceras de seguridad en todas las respuestas.

    Cabeceras (RNF-01.b, §2.2.5, §8 AM-10/AM-11):

    - ``Strict-Transport-Security`` (HSTS, configurable; por defecto
      ``max-age=31536000; includeSubDomains; preload``).
    - ``X-Frame-Options: DENY`` y CSP base con ``frame-ancestors 'none'``.
    - ``X-Content-Type-Options: nosniff`` y ``Referrer-Policy: no-referrer``.
    - ``Cache-Control: no-store, private`` + ``Pragma: no-cache`` (sin caché
      de datos, AM-10).
    - Redirección ``301 http → https`` si ``force_tls`` está activo (RNF-01.c).

    La negociación TLS 1.3 (OD-09/RNF-01.a) se fuerza en ``app/core/tls.py``
    o, cuando el TLS lo termina el edge, en la configuración del edge; aquí no
    existe ninguna rama que acepte TLS 1.2.
    """

    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.settings = settings

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if self.settings.force_tls and not self._is_tls(scope):
            await self._redirect_to_https(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["Strict-Transport-Security"] = self.settings.hsts_value
                headers["X-Frame-Options"] = X_FRAME_OPTIONS
                headers["X-Content-Type-Options"] = X_CONTENT_TYPE_OPTIONS
                headers["Referrer-Policy"] = REFERRER_POLICY
                # AM-11/AM-12 (T63): aislamiento de contexto de navegación y
                # anti-incrustación de recursos entre orígenes.
                headers["Cross-Origin-Opener-Policy"] = CROSS_ORIGIN_OPENER_POLICY
                headers["Cross-Origin-Resource-Policy"] = CROSS_ORIGIN_RESOURCE_POLICY
                headers["X-Permitted-Cross-Domain-Policies"] = X_PERMITTED_CROSS_DOMAIN_POLICIES
                headers["Cache-Control"] = CACHE_CONTROL_NO_STORE
                headers["Pragma"] = PRAGMA_NO_CACHE
                # Swagger UI/ReDoc necesitan CDN + inline script: CSP permisiva
                # solo en las rutas de docs cuando están habilitadas (T18/AM-11).
                path = scope.get("path", "")
                docs_enabled = self.settings.enable_docs and path in DOCS_PATHS
                headers["Content-Security-Policy"] = CSP_DOCS if docs_enabled else CSP_BASE
            await send(message)

        await self.app(scope, receive, send_with_headers)

    def _is_tls(self, scope: Scope) -> bool:
        if scope.get("scheme") == "https":
            return True
        return (Headers(scope=scope).get("X-Forwarded-Proto") or "").lower() == "https"

    async def _redirect_to_https(self, scope: Scope, receive: Receive, send: Send) -> None:
        # El loopback nunca se redirige (desarrollo local sin TLS).
        client = scope.get("client")
        host_ip = client[0] if client else ""
        if host_ip in ("127.0.0.1", "::1", "localhost"):
            await self.app(scope, receive, send)
            return
        host_header = Headers(scope=scope).get("host") or "localhost"
        path = scope.get("path", "/")
        response = Response(
            status_code=301,
            headers={"Location": f"https://{host_header}{path}"},
        )
        await response(scope, receive, send)


class CORSVaryMiddleware:
    """Garantiza ``Vary: Origin`` cuando hay allowlist CORS configurada (§2.2.2).

    ``CORSMiddleware`` emite ``Vary: Origin`` para orígenes permitidos, pero
    este middleware (el más externo) normaliza el valor a un único ``Origin``
    en **todas** las respuestas con CORS activo, incluso si se combinan varias
    capas. Con la allowlist vacía (deny-all) no añade la cabecera.
    """

    def __init__(self, app: ASGIApp, enabled: bool) -> None:
        self.app = app
        self.enabled = enabled

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self.enabled:
            await self.app(scope, receive, send)
            return

        async def send_with_vary(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                existing = headers.get("vary")
                values = (
                    [value.strip() for value in existing.split(",") if value.strip()]
                    if existing
                    else []
                )
                if "origin" not in [value.lower() for value in values]:
                    values.append("Origin")
                headers["Vary"] = ", ".join(values)
            await send(message)

        await self.app(scope, receive, send_with_vary)
