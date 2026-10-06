"""Validación de esquema, rangos y catálogos de la ingesta del webhook (T25).

El origen es el webhook firmado de Apps Script (§10.1). Cuando este módulo se
invoca, el cuerpo ya está **deserializado a JSON** y la firma/frescura ya se
verificaron antes de interpretarlo (T23/T24).

Se valida, en este orden:

1. **Tamaño** del evento: ``> 256 KB`` plano ``/ > 64 KB`` comprimido → ``413``
   (RNF-12.f). El endpoint puede pasar el tamaño real del cuerpo (``raw_size``);
   si no, se mide serializando el documento.
2. **Sobre lógico** de ingesta: ``schema_version`` soportada, ``type``
   soportado si viene, ``event_id`` (UUID), ``doc_id``, ``data_date``,
   ``content_sha256`` (§10.1, §7.2).
3. **Catálogos fijos** de §7.3–§7.6 (fuente única: constantes de
   ``app.models.tables``): 4 KPIs, 5 unidades regionales, 3 turnos y ranking
   Top 5 (≤5 filas).
4. **JSON Schema** del contrato de mensajes
   (``contracts/messages/1.0.0.schema.json``): se reutiliza el subschema
   ``payload`` (§7.8), que es la parte que el origen envía; ``freshness`` y
   ``quality`` los calcula el backend y no viajan desde Apps Script.

Reglas de rechazo:

- KPI negativo, ``NaN``, ``Infinity`` o no numérico/no entero → ``422``.
- Unidad regional o turno **fuera de allowlist** → se **descarta** y se registra
  como ``rejected_unknown_unit`` / ``rejected_unknown_turno`` (RF-03.h) en la
  lista de rechazos auditables, **sin tumbar** la instantánea válida. La serie
  se normaliza a los catálogos canónicos (una unidad ausente se conserva en 0,
  RF-03.e).
- Ranking con más de 5 filas o ``puesto``/``top_n`` fuera de rango → ``422``.

El resultado (:class:`ValidatedSnapshot`) expone el payload **normalizado** y la
lista de rechazos para que la capa de ingesta (T26) los audite.
"""

from __future__ import annotations

import json
import math
import re
import uuid
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, NoReturn

import jsonschema
from pydantic import ValidationError

from app.config import get_settings
from app.core.errors import raise_http_error
from app.models.tables import KPIS, REGIONAL_UNITS, TURNOS
from app.schemas.consulta import CONSULTA_COLUMNS, ConsultaRow

# --- Contrato: versiones y tipos soportados (§7.8) ---------------------------
SCHEMA_VERSION = "1.0.0"
SUPPORTED_SCHEMA_VERSIONS: frozenset[str] = frozenset({SCHEMA_VERSION})
SUPPORTED_TYPES: frozenset[str] = frozenset({"indicators.snapshot"})

# --- Catálogos fijos (§7.3–§7.6) --------------------------------------------
REGIONAL_UNIT_LABELS: dict[str, str] = {
    "capital": "Capital",
    "sur": "Sur",
    "este": "Este",
    "oeste": "Oeste",
    "norte": "Norte",
}
RANKING_MAX_ROWS = 5

# Turnos canónicos con su ventana (§7.4); se usan al completar un turno ausente.
_TURNO_DEFAULTS: dict[str, dict[str, Any]] = {
    "MAÑANA": {"inicio_min": 360, "fin_min": 840, "label": "MAÑANA (06-14)"},
    "TARDE": {"inicio_min": 840, "fin_min": 1320, "label": "TARDE (14-22)"},
    "NOCHE": {"inicio_min": 1320, "fin_min": 360, "label": "NOCHE (22-06)"},
}

# --- Causas de rechazo auditables (RF-03.h) ---------------------------------
REJECTED_UNKNOWN_UNIT = "rejected_unknown_unit"
REJECTED_UNKNOWN_TURNO = "rejected_unknown_turno"
REJECTED_INVALID_KPI = "rejected_invalid_kpi"
REJECTED_INVALID_VALUE = "rejected_invalid_value"
REJECTED_INVALID_RANKING = "rejected_invalid_ranking"
REJECTED_INVALID_EVENT_ID = "rejected_invalid_event_id"
REJECTED_INVALID_DOC_ID = "rejected_invalid_doc_id"
REJECTED_INVALID_DATA_DATE = "rejected_invalid_data_date"
REJECTED_INVALID_CONTENT_HASH = "rejected_invalid_content_sha256"
REJECTED_INVALID_CONSULTA = "rejected_invalid_consulta"

_CONTENT_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_DATA_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

_SCHEMA_PATH = Path(__file__).resolve().parents[3] / "contracts" / "messages" / "1.0.0.schema.json"


@dataclass(frozen=True)
class Rejection:
    """Rechazo auditable de un elemento del payload (no aborta la instantánea)."""

    code: str
    field: str
    detail: str


@dataclass(frozen=True)
class ValidatedSnapshot:
    """Snapshot de ingesta validado, con payload normalizado y rechazos.

    ``document`` es el cuerpo original (para persistir el evento); ``payload`` es
    el payload **normalizado** a los catálogos canónicos que se distribuye.
    """

    document: dict[str, Any]
    event_id: uuid.UUID
    doc_id: str
    data_date: date
    content_sha256: str
    payload: dict[str, Any]
    rejections: tuple[Rejection, ...] = field(default_factory=tuple)
    schema_version: str = SCHEMA_VERSION
    type: str = "indicators.snapshot"

    @property
    def rejected_codes(self) -> tuple[str, ...]:
        """Códigos de causa de los rechazos auditables (para auditoría)."""
        return tuple(rejection.code for rejection in self.rejections)


def _reject(cause: str, message: str) -> NoReturn:
    """Rechaza con ``422`` usando una causa estable ``rejected_*`` (auditable)."""
    raise_http_error(cause, message, status_code=422)


@lru_cache(maxsize=1)
def _load_schema() -> dict[str, Any]:
    """Carga el JSON Schema del contrato (una sola vez por proceso)."""
    try:
        with _SCHEMA_PATH.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        raise_http_error("INTERNAL", "Esquema de mensajes no disponible en el backend.")


@lru_cache(maxsize=1)
def _payload_schema() -> dict[str, Any]:
    """Subschema de ``payload`` de ingesta derivado del contrato de mensajes.

    ``freshness``/``quality`` los calcula el backend (§7.7) y no viajan desde el
    origen, por lo que solo se exigen las cuatro secciones enviadas
    (``kpis``/``regional``/``turnos``/``ranking``), reutilizando los ``$defs``
    del mismo contrato (catálogos y rangos de §7.3–§7.6).
    """
    schema = _load_schema()
    payload = schema["properties"]["payload"]
    return {
        "$defs": schema.get("$defs", {}),
        "type": "object",
        "additionalProperties": False,
        "required": ["kpis", "regional", "turnos", "ranking"],
        "properties": {
            "kpis": payload["properties"]["kpis"],
            "regional": payload["properties"]["regional"],
            "turnos": payload["properties"]["turnos"],
            "ranking": payload["properties"]["ranking"],
            "consultas": _consultas_schema(),
        },
    }


def _consultas_schema() -> dict[str, Any]:
    """Subschema de la sección opcional ``consultas`` (20 columnas de CONSULTAS)."""
    properties: dict[str, Any] = {
        name: {"type": "string"} for name in CONSULTA_COLUMNS if name != "fecha_consulta"
    }
    properties["fecha_consulta"] = {"type": "string", "pattern": _DATA_DATE_RE.pattern}
    return {
        "type": "array",
        "items": {
            "type": "object",
            "additionalProperties": False,
            "required": ["fecha_consulta"],
            "properties": properties,
        },
    }


# ---------------------------------------------------------------------------
# Tamaño (RNF-12.f)
# ---------------------------------------------------------------------------
def measure_size_bytes(document: Any) -> int:
    """Tamaño en bytes de la representación JSON compacta del documento."""
    return len(json.dumps(document, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))


def enforce_size_limit(
    size_bytes: int,
    *,
    compressed: bool = False,
    max_plain_bytes: int | None = None,
    max_compressed_bytes: int | None = None,
) -> None:
    """Aplica el límite de payload (256 KB plano / 64 KB comprimido) → ``413``."""
    settings = get_settings()
    if compressed:
        limit = (
            max_compressed_bytes
            if max_compressed_bytes is not None
            else settings.max_payload_compressed_bytes
        )
    else:
        limit = (
            max_plain_bytes if max_plain_bytes is not None else settings.max_payload_plaintext_bytes
        )
    if size_bytes > limit:
        raise_http_error(
            "PAYLOAD_TOO_LARGE",
            "Payload supera el límite (256 KB plano / 64 KB comprimido).",
        )


# ---------------------------------------------------------------------------
# Validación de catálogos y rangos
# ---------------------------------------------------------------------------
def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_finite_number(value: Any) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _require_non_negative_int(value: Any, cause: str) -> None:
    """Exige un entero no negativo (rechaza float/NaN/Infinity/bool, RNF-15.b)."""
    if not _is_int(value) or value < 0:
        _reject(cause, "Valor numérico inválido (se espera entero no negativo).")


def _assert_finite(payload: Any) -> None:
    """Rechaza ``NaN``/``Infinity`` en cualquier parte del payload (RNF-15.b)."""
    stack: list[Any] = [payload]
    while stack:
        current = stack.pop()
        if isinstance(current, float):
            if not math.isfinite(current):
                _reject(REJECTED_INVALID_VALUE, "El payload contiene NaN/Infinity.")
        elif isinstance(current, dict):
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)


def _validate_kpis(kpis: Any) -> None:
    if not isinstance(kpis, dict) or set(kpis.keys()) != set(KPIS):
        _reject(REJECTED_INVALID_KPI, "Catálogo de KPIs inválido (se esperan 4).")
    for key in KPIS:
        kpi = kpis[key]
        if not isinstance(kpi, dict):
            _reject(REJECTED_INVALID_KPI, f"KPI '{key}' inválido.")
        _require_non_negative_int(kpi.get("value"), REJECTED_INVALID_KPI)
        _require_non_negative_int(kpi.get("baseline_value"), REJECTED_INVALID_KPI)
        delta_abs = kpi.get("delta_abs")
        if delta_abs is not None and not _is_int(delta_abs):
            _reject(REJECTED_INVALID_KPI, f"delta_abs de '{key}' no es entero.")
        delta_pct = kpi.get("delta_pct")
        if delta_pct is not None and not _is_finite_number(delta_pct):
            _reject(REJECTED_INVALID_KPI, f"delta_pct de '{key}' no es numérico.")


def _normalize_regional(regional: Any, rejections: list[Rejection]) -> list[dict[str, Any]]:
    """Filtra unidades fuera de allowlist y completa el catálogo canónico."""
    if not isinstance(regional, list):
        _reject(REJECTED_UNKNOWN_UNIT, "Serie regional inválida.")

    by_unit: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(regional):
        field_path = f"regional[{index}].unidad_id"
        if not isinstance(item, dict):
            rejections.append(
                Rejection(REJECTED_UNKNOWN_UNIT, f"regional[{index}]", "Entrada no es objeto.")
            )
            continue
        unidad = item.get("unidad_id")
        if unidad not in REGIONAL_UNITS:
            rejections.append(
                Rejection(
                    REJECTED_UNKNOWN_UNIT,
                    field_path,
                    f"Unidad '{unidad}' fuera de la allowlist; descartada.",
                )
            )
            continue
        if unidad in by_unit:
            rejections.append(
                Rejection(
                    REJECTED_UNKNOWN_UNIT,
                    field_path,
                    f"Unidad '{unidad}' duplicada; descartada.",
                )
            )
            continue
        by_unit[unidad] = item

    normalized: list[dict[str, Any]] = []
    for position, unidad in enumerate(REGIONAL_UNITS, start=1):
        item = by_unit.get(unidad)
        if item is None:
            # RF-03.e: la categoría ausente se conserva con barra 0.
            item = {
                "unidad_id": unidad,
                "label": REGIONAL_UNIT_LABELS[unidad],
                "intervenciones": 0,
                "variacion_abs": 0,
                "variacion_pct": 0.0,
                "rank": position,
            }
        _require_non_negative_int(item.get("intervenciones"), REJECTED_INVALID_VALUE)
        normalized.append(item)
    return normalized


def _normalize_turnos(turnos: Any, rejections: list[Rejection]) -> list[dict[str, Any]]:
    """Filtra turnos fuera de allowlist y devuelve el orden cronológico canónico."""
    if not isinstance(turnos, list):
        _reject(REJECTED_UNKNOWN_TURNO, "Serie de turnos inválida.")

    by_turno: dict[str, dict[str, Any]] = {}
    for index, item in enumerate(turnos):
        field_path = f"turnos[{index}].turno_id"
        if not isinstance(item, dict):
            rejections.append(
                Rejection(REJECTED_UNKNOWN_TURNO, f"turnos[{index}]", "Entrada no es objeto.")
            )
            continue
        turno = item.get("turno_id")
        if turno not in TURNOS:
            rejections.append(
                Rejection(
                    REJECTED_UNKNOWN_TURNO,
                    field_path,
                    f"Turno '{turno}' fuera de la allowlist; descartado.",
                )
            )
            continue
        if turno in by_turno:
            rejections.append(
                Rejection(
                    REJECTED_UNKNOWN_TURNO,
                    field_path,
                    f"Turno '{turno}' duplicado; descartado.",
                )
            )
            continue
        by_turno[turno] = item

    normalized: list[dict[str, Any]] = []
    for turno in TURNOS:
        item = by_turno.get(turno)
        if item is None:
            defaults = _TURNO_DEFAULTS[turno]
            item = {
                "turno_id": turno,
                "inicio_min": defaults["inicio_min"],
                "fin_min": defaults["fin_min"],
                "label": defaults["label"],
                "intervenciones": 0,
                "variacion_abs": 0,
                "variacion_pct": 0.0,
                "estado": "pendiente",
            }
        _require_non_negative_int(item.get("intervenciones"), REJECTED_INVALID_VALUE)
        normalized.append(item)
    return normalized


def _validate_ranking(ranking: Any) -> None:
    if not isinstance(ranking, dict):
        _reject(REJECTED_INVALID_RANKING, "Ranking inválido.")
    top_n = ranking.get("top_n")
    if not _is_int(top_n) or top_n < 1 or top_n > RANKING_MAX_ROWS:
        _reject(REJECTED_INVALID_RANKING, "top_n fuera de rango (1..5).")
    dependencias = ranking.get("dependencias")
    if not isinstance(dependencias, list) or len(dependencias) > RANKING_MAX_ROWS:
        _reject(REJECTED_INVALID_RANKING, "Ranking con más de 5 dependencias.")
    for index, dep in enumerate(dependencias):
        if not isinstance(dep, dict):
            _reject(REJECTED_INVALID_RANKING, f"Dependencia #{index + 1} inválida.")
        _require_non_negative_int(dep.get("intervenciones"), REJECTED_INVALID_VALUE)
        puesto = dep.get("puesto")
        if not _is_int(puesto) or puesto < 1 or puesto > RANKING_MAX_ROWS:
            _reject(REJECTED_INVALID_RANKING, "puesto fuera de rango (1..5).")


def _normalize_consultas(consultas: Any, rejections: list[Rejection]) -> list[dict[str, Any]]:
    """Normaliza la hoja «CONSULTAS» (20 columnas) sin tumbar la instantánea.

    Una fila inválida se descarta y se registra como ``rejected_invalid_consulta``
    (RF-03.h); el resto se conserva. La sección es **opcional** (compatibilidad
    con orígenes aún sin la hoja).
    """
    if consultas is None:
        return []
    if not isinstance(consultas, list):
        rejections.append(
            Rejection(REJECTED_INVALID_CONSULTA, "consultas", "La sección no es una lista.")
        )
        return []

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(consultas):
        if not isinstance(item, dict):
            rejections.append(
                Rejection(
                    REJECTED_INVALID_CONSULTA,
                    f"consultas[{index}]",
                    "La fila no es un objeto.",
                )
            )
            continue
        try:
            row = ConsultaRow.model_validate(item)
        except ValidationError as exc:
            errors = exc.errors()
            detail = errors[0].get("msg", "fila inválida") if errors else "fila inválida"
            rejections.append(
                Rejection(REJECTED_INVALID_CONSULTA, f"consultas[{index}]", str(detail))
            )
            continue
        normalized.append(row.model_dump(mode="json"))
    return normalized


# ---------------------------------------------------------------------------
# Validación del documento completo
# ---------------------------------------------------------------------------
def _validate_envelope(document: dict[str, Any]) -> tuple[uuid.UUID, str, date, str, str, str]:
    """Valida los campos del sobre y devuelve los tipados."""
    schema_version = document.get("schema_version")
    if schema_version not in SUPPORTED_SCHEMA_VERSIONS:
        raise_http_error("BAD_REQUEST", "Versión de esquema no soportada.")

    message_type = document.get("type")
    if message_type is not None and message_type not in SUPPORTED_TYPES:
        raise_http_error("BAD_REQUEST", "Tipo de mensaje no soportado.")

    event_id_raw = document.get("event_id")
    try:
        event_id = uuid.UUID(str(event_id_raw))
    except (ValueError, TypeError, AttributeError):
        _reject(REJECTED_INVALID_EVENT_ID, "event_id inválido.")

    doc_id = document.get("doc_id")
    if not isinstance(doc_id, str) or not doc_id.strip():
        _reject(REJECTED_INVALID_DOC_ID, "doc_id inválido.")

    data_date_raw = document.get("data_date")
    if not isinstance(data_date_raw, str) or not _DATA_DATE_RE.match(data_date_raw):
        _reject(REJECTED_INVALID_DATA_DATE, "data_date inválido.")
    data_date = date.fromisoformat(data_date_raw)

    content_sha256 = document.get("content_sha256")
    if not isinstance(content_sha256, str) or not _CONTENT_SHA256_RE.match(content_sha256):
        _reject(REJECTED_INVALID_CONTENT_HASH, "content_sha256 inválido.")

    return (
        event_id,
        doc_id,
        data_date,
        content_sha256,
        str(schema_version),
        str(message_type or "indicators.snapshot"),
    )


def validate_snapshot(
    document: dict[str, Any],
    *,
    raw_size_bytes: int | None = None,
    compressed: bool = False,
) -> ValidatedSnapshot:
    """Valida el cuerpo deserializado (sobre + catálogos + JSON Schema).

    ``raw_size_bytes``/``compressed`` permiten aplicar el límite sobre el cuerpo
    tal como llegó (incluyendo una eventual compresión); si se omiten, se mide el
    documento serializado.
    """
    if not isinstance(document, dict):
        _reject("SNAPSHOT_INVALID", "Cuerpo de ingesta inválido.")

    enforce_size_limit(
        raw_size_bytes if raw_size_bytes is not None else measure_size_bytes(document),
        compressed=compressed,
    )

    (
        event_id,
        doc_id,
        data_date,
        content_sha256,
        schema_version,
        message_type,
    ) = _validate_envelope(document)

    payload = document.get("payload")
    if not isinstance(payload, dict):
        _reject("SNAPSHOT_INVALID", "Payload inválido.")
    required_sections = {"kpis", "regional", "turnos", "ranking"}
    supported_sections = required_sections | {"consultas"}
    if not required_sections.issubset(payload.keys()) or not set(payload.keys()).issubset(
        supported_sections
    ):
        _reject("SNAPSHOT_INVALID", "Secciones del payload no soportadas.")

    _assert_finite(payload)

    # Catálogos fijos: KPI negativo/NaN → 422; unidad/turno fuera de allowlist se
    # descarta y se audita sin tumbar la instantánea válida (RF-03.h).
    rejections: list[Rejection] = []
    _validate_kpis(payload.get("kpis"))
    normalized_regional = _normalize_regional(payload.get("regional"), rejections)
    normalized_turnos = _normalize_turnos(payload.get("turnos"), rejections)
    _validate_ranking(payload.get("ranking"))
    normalized_consultas = _normalize_consultas(payload.get("consultas"), rejections)

    normalized_payload: dict[str, Any] = {
        "kpis": payload["kpis"],
        "regional": normalized_regional,
        "turnos": normalized_turnos,
        "ranking": payload["ranking"],
        "consultas": normalized_consultas,
    }

    # Validación estructural contra el JSON Schema del contrato (§7.8).
    try:
        jsonschema.validate(normalized_payload, _payload_schema())
    except jsonschema.ValidationError:
        _reject("SNAPSHOT_INVALID", "Payload no cumple el esquema del contrato.")

    return ValidatedSnapshot(
        document=document,
        event_id=event_id,
        doc_id=doc_id,
        data_date=data_date,
        content_sha256=content_sha256,
        payload=normalized_payload,
        rejections=tuple(rejections),
        schema_version=schema_version,
        type=message_type,
    )
