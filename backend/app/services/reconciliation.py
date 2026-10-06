"""Reconciliación por polling de respaldo del origen Google Sheets (T45, RF-01.i).

Red de seguridad ante triggers perdidos o fallos del webhook (RISK-01/RISK-14):
un **job programado** lee el documento declarado con la **API de Google Sheets**
mediante una **service account de solo lectura**, calcula el ``content_sha256``
del contenido normalizado y lo compara con el último aceptado en
``app.snapshot_current``. Si difiere (hubo cambios no notificados por el
webhook), **emite el evento** reutilizando el mismo pipeline de ingesta
(validación T25 + persistencia idempotente T26 + redistribución T28), de modo
que **no se pierden datos** (RNF-06.f). El sistema sigue siendo unidireccional:
el backend nunca escribe en el documento.

El hash es idéntico al del Apps Script (T40): SHA-256 del JSON canónico de
``{schema_version, data_date, grid}`` donde ``grid`` son los valores de pantalla
(FORMATTED_VALUE) de las hojas vigiladas. Así la comparación es estable y no
depende del formato numérico.

El supervisor (:class:`SourceSupervisor`) orquesta este job y el monitor de
salud del origen (T46) con la cadencia configurada.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.core.errors import APIError
from app.core.logging import get_logger
from app.models.tables import KPIS, REGIONAL_UNITS, TURNOS, snapshot_current, webhook_registry
from app.services.audit import record_audit
from app.services.auth import WebhookIdentity
from app.services.bus import publish_snapshot
from app.services.db import get_session_factory
from app.services.ingest import persist_webhook
from app.services.source_health import evaluate_source_health
from app.services.validation import validate_snapshot

logger = get_logger(__name__)

SCHEMA_VERSION = "1.0.0"
SHEETS_SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"

#: Mapeo 1:1 hojas→series (OD-15), alineado con `apps-script/`.
SHEET_KPIS = "Resumen"
SHEET_REGIONAL = "Regional"
SHEET_TURNOS = "Turnos"
SHEET_RANKING = "Ranking"
SHEET_CONSULTAS = "CONSULTAS"
WATCHED_SHEETS: tuple[str, ...] = (SHEET_KPIS, SHEET_REGIONAL, SHEET_TURNOS, SHEET_RANKING)
#: Hojas opcionales: se leen y entran en el hash de contenido, pero no bloquean
#: la reconciliación si faltan (compatibilidad con documentos previos).
OPTIONAL_SHEETS: tuple[str, ...] = (SHEET_CONSULTAS,)
ALL_SHEETS: tuple[str, ...] = WATCHED_SHEETS + OPTIONAL_SHEETS

#: Cabeceras de la hoja «CONSULTAS»: display de la planilla → campo canónico.
CONSULTA_HEADER_MAP: dict[str, str] = {
    "fecha consulta": "fecha_consulta",
    "hora consulta": "hora_consulta",
    "turno": "turno",
    "jerarquía": "jerarquia",
    "jerarquia": "jerarquia",
    "personal policial": "personal_policial",
    "jefatura regional": "jefatura_regional",
    "dependencias": "dependencias",
    "tipo consulta": "tipo_consulta",
    "identificación": "identificacion",
    "identificacion": "identificacion",
    "tipo de arma/vehículo": "tipo_arma_vehiculo",
    "tipo de arma/vehiculo": "tipo_arma_vehiculo",
    "resultado": "resultado",
    "causas penales": "causas_penales",
    "registro/legajo": "registro_legajo",
    "autoridad judicial": "autoridad_judicial",
    "sistema utilizado": "sistema_utilizado",
    "trámite devuelto": "tramite_devuelto",
    "tramite devuelto": "tramite_devuelto",
    "hora resp": "hora_resp",
    "personal que informa": "personal_que_informa",
    "cargo": "cargo",
    "operativos preventivos": "operativos_preventivos",
}

#: Cabeceras obligatorias por hoja (allowlist, T39/OOS-06).
REQUIRED_HEADERS: dict[str, tuple[str, ...]] = {
    SHEET_KPIS: ("kpi_id", "value"),
    SHEET_REGIONAL: ("unidad_id", "intervenciones"),
    SHEET_TURNOS: ("turno_id", "intervenciones"),
    SHEET_RANKING: ("puesto", "dependencia_id", "comisaria", "intervenciones"),
}

KPI_LABELS: dict[str, str] = {
    "total_consultas_sifcop": "Total Consultas SIFCOP",
    "personas_capturadas": "Personas Capturadas",
    "vehiculos_secuestrados": "Vehículos Secuestrados",
    "armas_secuestradas": "Armas Secuestradas",
}
UNIT_LABELS: dict[str, str] = {
    "capital": "Capital",
    "sur": "Sur",
    "este": "Este",
    "oeste": "Oeste",
    "norte": "Norte",
}
TURNO_DEFAULTS: dict[str, dict[str, Any]] = {
    "MAÑANA": {"inicio_min": 360, "fin_min": 840, "label": "MAÑANA (06-14)"},
    "TARDE": {"inicio_min": 840, "fin_min": 1320, "label": "TARDE (14-22)"},
    "NOCHE": {"inicio_min": 1320, "fin_min": 360, "label": "NOCHE (22-06)"},
}
RANKING_MAX_ROWS = 5


class ReconciliationLayoutError(Exception):
    """El documento no cumple el layout allowlist (fail-closed, OOS-06)."""


def generate_uuid7() -> uuid.UUID:
    """Genera un UUIDv7 (RFC 9562) para ``event_id`` (clave de idempotencia).

    Mismo formato que la ingesta del webhook: 48 bits de timestamp Unix en ms,
    versión 7 y variante 10xx; el resto aleatorio.
    """
    ts_ms = int(time.time() * 1000) & ((1 << 48) - 1)
    rand = os.urandom(10)
    buf = bytearray(16)
    buf[0:6] = ts_ms.to_bytes(6, "big")
    buf[6] = (rand[0] & 0x0F) | 0x70
    buf[7] = rand[1]
    buf[8] = (rand[2] & 0x3F) | 0x80
    buf[9:16] = rand[3:10]
    return uuid.UUID(bytes=bytes(buf))


# =============================================================================
# Normalización y hash (idéntico al Apps Script)
# =============================================================================
def canonical_json(value: Any) -> str:
    """JSON canónico: claves ordenadas, sin espacios y sin escapar Unicode."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_sha256_from_grid(grid: dict[str, list[list[str]]], data_date: str, version: str) -> str:
    """SHA-256 hex del contenido normalizado (mismo algoritmo que T40)."""
    payload = {"schema_version": version, "data_date": data_date, "grid": grid}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _clean_grid(values: list[list[Any]]) -> list[list[str]]:
    """Normaliza la rejilla a cadenas y descarta filas sin contenido."""
    cleaned: list[list[str]] = []
    for index, row in enumerate(values):
        cells = ["" if cell is None else str(cell) for cell in row]
        if index == 0 or any(cell.strip() != "" for cell in cells):
            cleaned.append(cells)
    return cleaned


def _header_map(sheet: str, headers: list[str]) -> dict[str, int]:
    """Valida cabeceras obligatorias y devuelve el mapa ``cabecera → índice``."""
    index: dict[str, int] = {}
    for position, raw in enumerate(headers):
        name = str(raw).strip().lower()
        if name:
            index[name] = position
    missing = [name for name in REQUIRED_HEADERS[sheet] if name not in index]
    if missing:
        raise ReconciliationLayoutError(
            f"Layout inválido en '{sheet}': faltan cabeceras {missing}; no se adivinan columnas."
        )
    return index


def _cell(record: list[str], index: dict[str, int], name: str) -> str:
    position = index.get(name)
    if position is None or position >= len(record):
        return ""
    return record[position]


def _to_int(value: str | None, fallback: int = 0) -> int:
    if value is None or str(value).strip() == "":
        return fallback
    try:
        return max(0, int(float(str(value).replace(".", "").replace(",", "."))))
    except ValueError:
        return fallback


def _to_number(value: str | None, fallback: float = 0.0) -> float:
    if value is None or str(value).strip() == "":
        return fallback
    try:
        return float(str(value).replace(".", "").replace(",", "."))
    except ValueError:
        return fallback


def _round2(value: float) -> float:
    return round(value, 2)


def _rows(grid: dict[str, list[list[str]]], sheet: str) -> tuple[list[str], list[list[str]]]:
    values = grid.get(sheet) or []
    if not values:
        raise ReconciliationLayoutError(f"Falta la hoja '{sheet}' o está vacía.")
    return values[0], values[1:]


def build_payload_from_grid(grid: dict[str, list[list[str]]]) -> dict[str, Any]:
    """Normaliza la rejilla al payload canónico de ingesta (§7.3–§7.6 + CONSULTAS)."""
    return {
        "kpis": _normalize_kpis(grid),
        "regional": _normalize_regional(grid),
        "turnos": _normalize_turnos(grid),
        "ranking": _normalize_ranking(grid),
        "consultas": _normalize_consultas(grid),
    }


def _normalize_consulta_date(value: str) -> str:
    """Normaliza la fecha de la hoja a ISO (acepta ``DD/MM/YYYY`` y ``DD-MM-YYYY``)."""
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    return text


def _normalize_consultas(grid: dict[str, list[list[str]]]) -> list[dict[str, str]]:
    """Normaliza la hoja «CONSULTAS» (20 columnas oficiales) a campos canónicos."""
    if not grid.get(SHEET_CONSULTAS):
        return []
    headers, records = _rows(grid, SHEET_CONSULTAS)
    index: dict[str, int] = {}
    for position, raw in enumerate(headers):
        canonical = CONSULTA_HEADER_MAP.get(str(raw).strip().lower())
        if canonical and canonical not in index:
            index[canonical] = position
    if "fecha_consulta" not in index:
        raise ReconciliationLayoutError("Falta la cabecera 'Fecha Consulta' en la hoja CONSULTAS.")
    normalized: list[dict[str, str]] = []
    for record in records:
        raw_date = _cell(record, index, "fecha_consulta").strip()
        if not raw_date:
            continue
        row: dict[str, str] = {"fecha_consulta": _normalize_consulta_date(raw_date)}
        for canonical in set(CONSULTA_HEADER_MAP.values()):
            if canonical == "fecha_consulta":
                continue
            row[canonical] = _cell(record, index, canonical).strip()
        normalized.append(row)
    return normalized


def _normalize_kpis(grid: dict[str, list[list[str]]]) -> dict[str, Any]:
    headers, records = _rows(grid, SHEET_KPIS)
    index = _header_map(SHEET_KPIS, headers)
    by_id: dict[str, list[str]] = {}
    for record in records:
        kpi_id = _cell(record, index, "kpi_id").strip()
        if kpi_id in by_id:
            raise ReconciliationLayoutError(f"KPI duplicado '{kpi_id}'.")
        by_id[kpi_id] = record
    now = datetime.now(timezone.utc).isoformat()
    kpis: dict[str, Any] = {}
    for kpi_id in KPIS:
        record = by_id.get(kpi_id)
        if record is None:
            raise ReconciliationLayoutError(f"Falta el KPI '{kpi_id}' (se esperan los 4).")
        raw_value = _cell(record, index, "value").strip()
        if raw_value == "":
            raise ReconciliationLayoutError(f"KPI '{kpi_id}' sin 'value'.")
        value = _to_int(raw_value)
        raw_baseline = _cell(record, index, "baseline_value").strip()
        has_reference = raw_baseline != ""
        baseline = _to_int(raw_baseline, value) if has_reference else value
        delta_abs: int | None = value - baseline if has_reference else None
        delta_pct: float | None = None
        if has_reference and baseline != 0:
            delta_pct = _round2((delta_abs or 0) / baseline * 100)
        direction = _cell(record, index, "direction").strip().lower()
        if direction not in ("up", "down", "flat"):
            delta = delta_abs or 0
            direction = "up" if delta > 0 else ("down" if delta < 0 else "flat")
        kpis[kpi_id] = {
            "label": _cell(record, index, "label").strip() or KPI_LABELS[kpi_id],
            "value": value,
            "delta_abs": delta_abs,
            "delta_pct": delta_pct,
            "direction": direction,
            "comparison": "ayer_mismo_tramo",
            "baseline_value": baseline,
            "as_of": _cell(record, index, "as_of").strip() or now,
            "has_reference": has_reference,
        }
    return kpis


def _normalize_regional(grid: dict[str, list[list[str]]]) -> list[dict[str, Any]]:
    headers, records = _rows(grid, SHEET_REGIONAL)
    index = _header_map(SHEET_REGIONAL, headers)
    by_unit: dict[str, list[str]] = {}
    for record in records:
        unit = _cell(record, index, "unidad_id").strip().lower()
        if unit not in REGIONAL_UNITS:
            raise ReconciliationLayoutError(f"Unidad regional fuera de allowlist: '{unit}'.")
        by_unit[unit] = record
    items: list[dict[str, Any]] = []
    for unit in REGIONAL_UNITS:
        record = by_unit.get(unit)
        label = (_cell(record, index, "label").strip() if record else "") or UNIT_LABELS[unit]
        intervenciones = _to_int(_cell(record, index, "intervenciones")) if record else 0
        variacion_abs = _to_int(_cell(record, index, "variacion_abs")) if record else 0
        variacion_pct = _round2(_to_number(_cell(record, index, "variacion_pct"))) if record else 0
        items.append(
            {
                "unidad_id": unit,
                "label": label,
                "intervenciones": intervenciones,
                "variacion_abs": variacion_abs,
                "variacion_pct": variacion_pct,
                "rank": 1,
            }
        )
    ordered = sorted(items, key=lambda item: (-int(item["intervenciones"]), str(item["label"])))
    for position, item in enumerate(ordered, start=1):
        item["rank"] = position
    return items


def _normalize_turnos(grid: dict[str, list[list[str]]]) -> list[dict[str, Any]]:
    headers, records = _rows(grid, SHEET_TURNOS)
    index = _header_map(SHEET_TURNOS, headers)
    by_turno: dict[str, list[str]] = {}
    for record in records:
        turno = _cell(record, index, "turno_id").strip().upper()
        if turno not in TURNOS:
            raise ReconciliationLayoutError(f"Turno fuera de allowlist: '{turno}'.")
        by_turno[turno] = record
    items: list[dict[str, Any]] = []
    for turno in TURNOS:
        record = by_turno.get(turno)
        defaults = TURNO_DEFAULTS[turno]
        estado = _cell(record, index, "estado").strip().lower() if record else ""
        if estado not in ("pendiente", "en_curso", "cerrada"):
            estado = _derive_estado(defaults, get_settings().canonical_timezone)
        label = (_cell(record, index, "label").strip() if record else "") or defaults["label"]
        intervenciones = _to_int(_cell(record, index, "intervenciones")) if record else 0
        variacion_abs = _to_int(_cell(record, index, "variacion_abs")) if record else 0
        variacion_pct = _round2(_to_number(_cell(record, index, "variacion_pct"))) if record else 0
        items.append(
            {
                "turno_id": turno,
                "inicio_min": _to_int(_cell(record, index, "inicio_min"), defaults["inicio_min"]),
                "fin_min": _to_int(_cell(record, index, "fin_min"), defaults["fin_min"]),
                "label": label,
                "intervenciones": intervenciones,
                "variacion_abs": variacion_abs,
                "variacion_pct": variacion_pct,
                "estado": estado,
            }
        )
    return items


def _normalize_ranking(grid: dict[str, list[list[str]]]) -> dict[str, Any]:
    headers, records = _rows(grid, SHEET_RANKING)
    index = _header_map(SHEET_RANKING, headers)
    if len(records) > RANKING_MAX_ROWS:
        raise ReconciliationLayoutError(
            f"El ranking tiene {len(records)} filas; el máximo es {RANKING_MAX_ROWS}."
        )
    deps: list[dict[str, Any]] = []
    for record in records:
        dep_id = _cell(record, index, "dependencia_id").strip()
        comisaria = _cell(record, index, "comisaria").strip()
        if not dep_id or not comisaria:
            raise ReconciliationLayoutError(
                "Cada fila del ranking requiere dependencia_id y comisaria."
            )
        deps.append(
            {
                "dependencia_id": dep_id,
                "comisaria": comisaria,
                "intervenciones": _to_int(_cell(record, index, "intervenciones")),
                "variacion_abs": _to_int(_cell(record, index, "variacion_abs")),
                "variacion_pct": _round2(_to_number(_cell(record, index, "variacion_pct"))),
                "puesto_previo": _to_int(_cell(record, index, "puesto_previo")),
            }
        )
    deps.sort(key=lambda item: (-int(item["intervenciones"]), str(item["comisaria"])))
    for position, dep in enumerate(deps, start=1):
        dep["puesto"] = position
        previous = int(dep["puesto_previo"])
        if previous < 1 or previous > RANKING_MAX_ROWS:
            dep["puesto_previo"] = position
    return {"top_n": max(1, min(RANKING_MAX_ROWS, len(deps))), "dependencias": deps}


def _local_now(tz: str) -> datetime:
    from zoneinfo import ZoneInfo

    try:
        return datetime.now(timezone.utc).astimezone(ZoneInfo(tz))
    except Exception:
        return datetime.now(timezone.utc)


def _canonical_date(tz: str) -> str:
    return _local_now(tz).date().isoformat()


def _derive_estado(defaults: dict[str, Any], tz: str) -> str:
    inicio = int(defaults["inicio_min"])
    fin = int(defaults["fin_min"])
    local = _local_now(tz)
    minute = local.hour * 60 + local.minute
    if fin > inicio:
        if inicio <= minute < fin:
            return "en_curso"
        return "pendiente" if minute < inicio else "cerrada"
    return "en_curso" if (minute >= inicio or minute < fin) else "pendiente"


# =============================================================================
# Cliente de solo lectura (service account)
# =============================================================================
@dataclass(frozen=True)
class ReconciledDocument:
    """Documento remoto normalizado y su hash de contenido."""

    doc_id: str
    document: dict[str, Any]
    content_sha256: str


@runtime_checkable
class SheetsReadClient(Protocol):
    """Cliente de solo lectura del documento de Google Sheets."""

    async def fetch_document(self, doc_id: str) -> ReconciledDocument | None:
        """Devuelve el documento normalizado o ``None`` si no está disponible."""
        ...


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


class ServiceAccountSheetsClient:
    """Cliente de la API de Google Sheets con service account de solo lectura.

    La credencial (JSON) se inyecta desde el secret manager (RNF-13.a) y **nunca**
    se registra. Solo se solicita el scope ``spreadsheets.readonly``.
    """

    def __init__(
        self,
        credentials: str,
        *,
        api_base: str = "https://sheets.googleapis.com/v4",
        range_suffix: str = "",
        timeout_seconds: float = 10.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_base = api_base.rstrip("/")
        self._range_suffix = range_suffix
        self._timeout = timeout_seconds
        self._client = client
        self._owns_client = client is None
        self._access_token: str | None = None
        self._token_expiry: float = 0.0
        self._credentials = self._load_credentials(credentials)

    @staticmethod
    def _load_credentials(credentials: str) -> dict[str, Any]:
        raw = credentials.strip()
        if not raw:
            raise ValueError("Credenciales de Google vacías.")
        if raw.startswith("{"):
            parsed: Any = json.loads(raw)
        elif os.path.isfile(raw):
            with open(raw, "r", encoding="utf-8") as handle:
                parsed = json.load(handle)
        else:
            raise ValueError("GOOGLE_SERVICE_ACCOUNT_JSON no es JSON ni una ruta válida.")
        if not isinstance(parsed, dict):
            raise ValueError("Credenciales de Google malformadas.")
        for field_name in ("client_email", "private_key", "token_uri"):
            if not parsed.get(field_name):
                raise ValueError(f"Credenciales de Google incompletas: falta '{field_name}'.")
        return parsed

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    def _sign_assertion(self) -> str:
        key = serialization.load_pem_private_key(
            str(self._credentials["private_key"]).encode("utf-8"), password=None
        )
        if not isinstance(key, rsa.RSAPrivateKey):
            raise ValueError("La service account requiere una clave RSA.")
        issued_at = int(time.time())
        header = {"alg": "RS256", "typ": "JWT"}
        claims = {
            "iss": self._credentials["client_email"],
            "scope": SHEETS_SCOPE,
            "aud": self._credentials["token_uri"],
            "iat": issued_at,
            "exp": issued_at + 3600,
        }
        header_b64 = _b64url(json.dumps(header, separators=(",", ":")).encode("utf-8"))
        claims_b64 = _b64url(json.dumps(claims, separators=(",", ":")).encode("utf-8"))
        signing_input = f"{header_b64}.{claims_b64}"
        signature = key.sign(signing_input.encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
        return f"{signing_input}.{_b64url(signature)}"

    async def _access_token_value(self) -> str:
        now = time.time()
        if self._access_token is not None and now < self._token_expiry - 30:
            return self._access_token
        client = await self._http()
        response = await client.post(
            str(self._credentials["token_uri"]),
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                "assertion": self._sign_assertion(),
            },
        )
        response.raise_for_status()
        body = response.json()
        token = body.get("access_token")
        if not isinstance(token, str) or not token:
            raise ValueError("El proveedor no devolvió access_token.")
        self._access_token = token
        expires_in = body.get("expires_in", 3600)
        self._token_expiry = now + int(expires_in if isinstance(expires_in, (int, float)) else 3600)
        return token

    async def fetch_document(self, doc_id: str) -> ReconciledDocument | None:
        """Lee el documento (solo lectura) y lo normaliza.

        Devuelve ``None`` si la API no responde o el documento no es legible; los
        errores de layout se propagan como :class:`ReconciliationLayoutError`.
        """
        token = await self._access_token_value()
        client = await self._http()
        ranges = [f"{sheet}{self._range_suffix}" for sheet in ALL_SHEETS]
        params: list[tuple[str, str]] = [("ranges", rng) for rng in ranges]
        params.extend([("majorDimension", "ROWS"), ("valueRenderOption", "FORMATTED_VALUE")])
        response = await client.get(
            f"{self._api_base}/spreadsheets/{doc_id}/values:batchGet",
            params=params,
            headers={"Authorization": f"Bearer {token}"},
        )
        if response.status_code in (401, 403):
            raise PermissionError("La service account no puede leer el documento (RISK-15).")
        response.raise_for_status()
        body = response.json()

        grid: dict[str, list[list[str]]] = {}
        for item in body.get("valueRanges", []):
            if not isinstance(item, dict):
                continue
            sheet_name = str(item.get("range", "")).split("!")[0].strip("'")
            values = item.get("values") or []
            if sheet_name in ALL_SHEETS:
                grid[sheet_name] = _clean_grid(values)
        for sheet in ALL_SHEETS:
            grid.setdefault(sheet, [])

        data_date = _canonical_date(get_settings().canonical_timezone)
        payload = build_payload_from_grid(grid) if all(grid.get(s) for s in WATCHED_SHEETS) else {}
        if not payload:
            return None
        content_hash = content_sha256_from_grid(grid, data_date, SCHEMA_VERSION)
        document = {
            "schema_version": SCHEMA_VERSION,
            "type": "indicators.snapshot",
            "event_id": str(generate_uuid7()),
            "doc_id": doc_id,
            "sheet_modified_at": datetime.now(timezone.utc).isoformat(),
            "data_date": data_date,
            "tz": get_settings().canonical_timezone,
            "content_sha256": content_hash,
            "payload": payload,
        }
        return ReconciledDocument(doc_id=doc_id, document=document, content_sha256=content_hash)

    async def aclose(self) -> None:
        if self._client is not None and self._owns_client:
            await self._client.aclose()
        self._client = None


# =============================================================================
# Reconciliación
# =============================================================================
@dataclass
class ReconciliationResult:
    """Resultado de reconciliar un documento."""

    doc_id: str
    status: str
    remote_hash: str | None = None
    current_hash: str | None = None
    event_id: str | None = None
    detail: str = ""


async def _current_content_hash(session: AsyncSession, doc_id: str) -> str | None:
    row = (
        await session.execute(
            select(snapshot_current.c.payload).where(snapshot_current.c.doc_id == doc_id)
        )
    ).first()
    if row is None:
        return None
    payload = row[0]
    if isinstance(payload, dict):
        value = payload.get("content_sha256")
        return str(value) if value else None
    return None


async def reconcile_document(
    session: AsyncSession,
    reader: SheetsReadClient,
    *,
    webhook_row: Any,
    correlation_id: str = "",
    now: datetime | None = None,
) -> ReconciliationResult:
    """Compara el hash remoto con el último aceptado y emite el evento si difiere."""
    doc_id = str(webhook_row.doc_id)
    momento = now or datetime.now(timezone.utc)
    remote = await reader.fetch_document(doc_id)
    if remote is None:
        return ReconciliationResult(doc_id=doc_id, status="unavailable")

    current_hash = await _current_content_hash(session, doc_id)
    if current_hash is not None and current_hash.lower() == remote.content_sha256.lower():
        return ReconciliationResult(
            doc_id=doc_id,
            status="unchanged",
            remote_hash=remote.content_sha256,
            current_hash=current_hash,
        )

    try:
        validated = validate_snapshot(remote.document)
    except APIError as exc:
        await record_audit(
            actor="source-reconciler",
            action="source.reconcile.rejected",
            resource=exc.code,
            result="rejected",
            correlation_id=correlation_id,
            session=session,
        )
        return ReconciliationResult(
            doc_id=doc_id,
            status="rejected",
            remote_hash=remote.content_sha256,
            current_hash=current_hash,
            detail=exc.code,
        )

    identity = WebhookIdentity(
        webhook_id=str(webhook_row.webhook_id),
        key_id="reconciliation",
        doc_id=doc_id,
        room_id=str(webhook_row.room_id or get_settings().default_room_id),
        nonce="reconciliation",
        timestamp=momento,
        version=SCHEMA_VERSION,
        schema_version=SCHEMA_VERSION,
        content_sha256=remote.content_sha256,
    )
    result = await persist_webhook(
        session,
        identity=identity,
        validated=validated,
        raw_body=json.dumps(remote.document).encode("utf-8"),
        correlation_id=correlation_id,
    )
    await session.commit()

    if not result.duplicate:
        try:
            await publish_snapshot(
                session=session,
                document=validated.document,
                seq=result.seq,
                room_id=identity.room_id,
                webhook_id=identity.webhook_id,
                correlation_id=correlation_id,
                accepted_at=momento,
            )
        except Exception:
            logger.warning(
                "reconcile_publish_failed",
                extra={"event": "source.reconcile", "result": "publish_error"},
            )
        await record_audit(
            actor="source-reconciler",
            action="source.reconcile.ingested",
            resource=doc_id,
            result="success",
            correlation_id=correlation_id,
        )

    return ReconciliationResult(
        doc_id=doc_id,
        status="duplicate" if result.duplicate else "ingested",
        remote_hash=remote.content_sha256,
        current_hash=current_hash,
        event_id=str(validated.event_id),
    )


async def run_reconciliation_once(
    session: AsyncSession,
    *,
    reader: SheetsReadClient | None = None,
    correlation_id: str = "",
    now: datetime | None = None,
) -> list[ReconciliationResult]:
    """Reconcilia todos los webhooks activos una vez (job programado, T45)."""
    active_reader = reader
    if active_reader is None:
        return []
    momento = now or datetime.now(timezone.utc)
    rows = (
        await session.execute(
            select(
                webhook_registry.c.webhook_id,
                webhook_registry.c.doc_id,
                webhook_registry.c.room_id,
            ).where(
                webhook_registry.c.estado == "activo",
                webhook_registry.c.revoked_at.is_(None),
            )
        )
    ).all()
    results: list[ReconciliationResult] = []
    for row in rows:
        try:
            result = await reconcile_document(
                session,
                active_reader,
                webhook_row=row,
                correlation_id=correlation_id,
                now=momento,
            )
        except ReconciliationLayoutError as exc:
            await session.rollback()
            await record_audit(
                actor="source-reconciler",
                action="source.reconcile.rejected",
                resource=str(row.doc_id),
                result="rejected",
                correlation_id=correlation_id,
            )
            result = ReconciliationResult(
                doc_id=str(row.doc_id), status="rejected", detail=str(exc)
            )
        except PermissionError as exc:
            await session.rollback()
            result = ReconciliationResult(
                doc_id=str(row.doc_id), status="unavailable", detail=str(exc)
            )
        except Exception:
            await session.rollback()
            logger.warning(
                "reconcile_failed",
                extra={"event": "source.reconcile", "result": "error"},
            )
            result = ReconciliationResult(doc_id=str(row.doc_id), status="error")
        results.append(result)
    return results


def build_sheets_reader(settings: Settings) -> SheetsReadClient | None:
    """Construye el cliente de reconciliación si la service account está configurada."""
    if not settings.google_service_account_json:
        return None
    try:
        return ServiceAccountSheetsClient(
            settings.google_service_account_json,
            api_base=settings.google_sheets_api_base,
            range_suffix=settings.google_sheets_range_suffix,
        )
    except ValueError:
        logger.warning(
            "reconciliation_client_invalid",
            extra={"event": "source.reconcile", "result": "config_error"},
        )
        return None


# =============================================================================
# Supervisor (job programado: reconciliación + salud del origen)
# =============================================================================
@dataclass
class SourceSupervisor:
    """Ejecuta periódicamente la reconciliación (T45) y el monitor de salud (T46)."""

    settings: Settings
    reader: SheetsReadClient | None = None
    _task: asyncio.Task[None] | None = field(default=None, init=False, repr=False)

    async def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run(), name="source-supervisor")

    async def _run(self) -> None:
        health_interval = max(5, int(self.settings.source_health_monitor_seconds))
        reconcile_interval = max(5, int(self.settings.reconciliation_interval_seconds))
        next_health = 0.0
        next_reconcile = 0.0
        while True:
            try:
                now = time.monotonic()
                if now >= next_health:
                    await self._evaluate_health()
                    next_health = now + health_interval
                if (
                    self.settings.reconciliation_enabled
                    and self.reader is not None
                    and now >= next_reconcile
                ):
                    await self._reconcile()
                    next_reconcile = now + reconcile_interval
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning(
                    "source_supervisor_error",
                    extra={"event": "source_supervisor", "result": "error"},
                )
            await asyncio.sleep(5.0)

    async def _evaluate_health(self) -> None:
        session_factory = get_session_factory()
        async with session_factory() as session:
            await evaluate_source_health(session)
            await session.commit()

    async def _reconcile(self) -> None:
        session_factory = get_session_factory()
        async with session_factory() as session:
            await run_reconciliation_once(session, reader=self.reader)
            await session.commit()

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        if isinstance(self.reader, ServiceAccountSheetsClient):
            await self.reader.aclose()


_supervisor: SourceSupervisor | None = None


def get_source_supervisor() -> SourceSupervisor:
    """Supervisor compartido (singleton por proceso)."""
    global _supervisor
    if _supervisor is None:
        settings = get_settings()
        _supervisor = SourceSupervisor(settings=settings, reader=build_sheets_reader(settings))
    return _supervisor


async def close_source_supervisor() -> None:
    """Detiene el supervisor (shutdown del lifespan)."""
    global _supervisor
    if _supervisor is not None:
        await _supervisor.stop()
        _supervisor = None
