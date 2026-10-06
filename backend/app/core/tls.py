"""Terminación TLS 1.3 del backend (OD-09, RNF-01.a).

El TLS se termina en el edge (Cloudflare/WAF), que debe configurarse
**"TLS 1.3 only"**. Cuando el backend sirve TLS directamente, esta utilidad
construye un ``ssl.SSLContext`` que **solo** negocia TLS 1.3: fija
``minimum_version = maximum_version = TLSv1_3``. No existe ninguna rama que
acepte TLS 1.2/1.1 (OD-09: "TLS 1.2 deshabilitado; sin ventana de
compatibilidad").

Arranque con TLS 1.3 (host/puerto/certificados desde el entorno, sin valores
hardcodeados)::

    py -m app.core.tls
"""

from __future__ import annotations

import ssl
from typing import Any, Callable

from app.config import Settings, get_settings

#: Versión mínima y máxima aceptada: SOLO TLS 1.3 (OD-09).
TLS_MIN_VERSION = ssl.TLSVersion.TLSv1_3


def build_tls_context(settings: Settings | None = None) -> ssl.SSLContext:
    """Devuelve un ``SSLContext`` que SOLO negocia TLS 1.3.

    Fijar ``minimum_version`` y ``maximum_version`` a ``TLSv1_3`` impide
    negociar TLS 1.2/1.1 y no deja ventana de compatibilidad (OD-09). El
    certificado y la llave se cargan desde rutas inyectadas por el entorno.
    """
    settings = settings or get_settings()
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = TLS_MIN_VERSION
    context.maximum_version = TLS_MIN_VERSION
    if settings.tls_certfile:
        context.load_cert_chain(
            certfile=settings.tls_certfile,
            keyfile=settings.tls_keyfile or None,
            password=settings.tls_keyfile_password or None,
        )
    if settings.tls_ca_certs:
        context.load_verify_locations(cafile=settings.tls_ca_certs)
    return context


def ssl_context_factory(
    config: Any, default_ssl_context_factory: Callable[[], ssl.SSLContext]
) -> ssl.SSLContext:
    """Factory de uvicorn (>=0.47) que fuerza TLS 1.3 en cada worker.

    Se ignora el contexto por defecto de uvicorn para no permitir TLS 1.2.
    """
    del config, default_ssl_context_factory
    return build_tls_context()


def serve() -> None:
    """Sirve ``app.main:app`` con TLS 1.3 (configuración desde entorno)."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        ssl_certfile=settings.tls_certfile or None,
        ssl_keyfile=settings.tls_keyfile or None,
        ssl_keyfile_password=settings.tls_keyfile_password or None,
        ssl_ca_certs=settings.tls_ca_certs or None,
        ssl_context_factory=ssl_context_factory,
    )


if __name__ == "__main__":
    serve()
