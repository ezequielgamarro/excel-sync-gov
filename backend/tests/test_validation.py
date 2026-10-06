"""Tests unitarios de la validación de esquema/rangos/catálogos (T25).

Cubre las reglas de la tarea T25:

- Cuerpo válido (ejemplo del contrato) → :class:`ValidatedSnapshot` normalizado.
- KPI negativo / NaN / no numérico → ``422``.
- Unidad regional y turno fuera de allowlist → ``rejected_*`` sin tumbar la
  instantánea (payload normalizado a los catálogos canónicos).
- Ranking con más de 5 filas / rango inválido → ``422``.
- Payload > 256 KB (plano) → ``413``; versión/tipo no soportados → ``400``.

Se puede ejecutar con pytest o directamente::

    py -m pytest backend/tests/test_validation.py
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

_BACKEND = Path(__file__).resolve().parents[1]
_REPO = _BACKEND.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.core.errors import APIError  # noqa: E402
from app.services.validation import (  # noqa: E402
    REJECTED_INVALID_KPI,
    REJECTED_INVALID_RANKING,
    REJECTED_UNKNOWN_TURNO,
    REJECTED_UNKNOWN_UNIT,
    ValidatedSnapshot,
    validate_snapshot,
)


def _example_message() -> dict:
    with (_REPO / "contracts" / "messages" / "1.0.0.example.json").open(
        "r", encoding="utf-8"
    ) as fh:
        return json.load(fh)


def _ingest_body() -> dict:
    """Cuerpo de ingesta §10.1 derivado del ejemplo del mensaje WSS."""
    message = _example_message()
    return {
        "schema_version": message["schema_version"],
        "event_id": message["event_id"],
        "doc_id": message["source"]["doc_id"],
        "sheet_modified_at": message["source"]["sheet_modified_at"],
        "data_date": message["data_date"],
        "tz": message["tz"],
        "content_sha256": message["source"]["content_sha256"],
        "payload": {
            key: copy.deepcopy(message["payload"][key])
            for key in ("kpis", "regional", "turnos", "ranking")
        },
    }


def test_valid_snapshot_normalizes_catalogs() -> None:
    validated = validate_snapshot(_ingest_body())
    assert isinstance(validated, ValidatedSnapshot)
    assert len(validated.payload["regional"]) == 5
    assert len(validated.payload["turnos"]) == 3
    assert set(validated.payload["kpis"]) == {
        "total_consultas_sifcop",
        "personas_capturadas",
        "vehiculos_secuestrados",
        "armas_secuestradas",
    }
    assert validated.rejections == ()


def test_negative_kpi_value_rejected_422() -> None:
    body = _ingest_body()
    body["payload"]["kpis"]["total_consultas_sifcop"]["value"] = -1
    with pytest.raises(APIError) as exc:
        validate_snapshot(body)
    assert exc.value.status_code == 422
    assert exc.value.code == REJECTED_INVALID_KPI


def test_nan_kpi_value_rejected_422() -> None:
    body = _ingest_body()
    body["payload"]["kpis"]["personas_capturadas"]["value"] = float("nan")
    with pytest.raises(APIError) as exc:
        validate_snapshot(body)
    assert exc.value.status_code == 422


def test_non_numeric_kpi_value_rejected_422() -> None:
    body = _ingest_body()
    body["payload"]["kpis"]["armas_secuestradas"]["value"] = "184732"
    with pytest.raises(APIError) as exc:
        validate_snapshot(body)
    assert exc.value.status_code == 422
    assert exc.value.code == REJECTED_INVALID_KPI


def test_unknown_unit_is_rejected_without_failing_snapshot() -> None:
    body = _ingest_body()
    body["payload"]["regional"][4]["unidad_id"] = "noreste"
    body["payload"]["regional"][4]["label"] = "Noreste"

    validated = validate_snapshot(body)

    assert REJECTED_UNKNOWN_UNIT in validated.rejected_codes
    # La instantánea sigue siendo válida y normalizada a las 5 unidades canónicas.
    assert len(validated.payload["regional"]) == 5
    unidad_ids = [item["unidad_id"] for item in validated.payload["regional"]]
    assert unidad_ids == ["capital", "sur", "este", "oeste", "norte"]
    assert "noreste" not in unidad_ids


def test_unknown_turno_is_rejected_without_failing_snapshot() -> None:
    body = _ingest_body()
    body["payload"]["turnos"][0]["turno_id"] = "MADRUGADA"

    validated = validate_snapshot(body)

    assert REJECTED_UNKNOWN_TURNO in validated.rejected_codes
    turno_ids = [item["turno_id"] for item in validated.payload["turnos"]]
    assert turno_ids == ["MAÑANA", "TARDE", "NOCHE"]


def test_ranking_with_more_than_five_rows_rejected_422() -> None:
    body = _ingest_body()
    ranking = body["payload"]["ranking"]
    ranking["dependencias"].append(copy.deepcopy(ranking["dependencias"][0]))
    with pytest.raises(APIError) as exc:
        validate_snapshot(body)
    assert exc.value.status_code == 422
    assert exc.value.code == REJECTED_INVALID_RANKING


def test_payload_too_large_rejected_413() -> None:
    with pytest.raises(APIError) as exc:
        validate_snapshot(_ingest_body(), raw_size_bytes=300_000)
    assert exc.value.status_code == 413
    assert exc.value.code == "PAYLOAD_TOO_LARGE"


def test_unsupported_schema_version_rejected_400() -> None:
    body = _ingest_body()
    body["schema_version"] = "2.0.0"
    with pytest.raises(APIError) as exc:
        validate_snapshot(body)
    assert exc.value.status_code == 400


def test_unsupported_type_rejected_400() -> None:
    body = _ingest_body()
    body["type"] = "heartbeat"
    with pytest.raises(APIError) as exc:
        validate_snapshot(body)
    assert exc.value.status_code == 400


# =============================================================================
# Sincronización del modelo de datos: hoja «CONSULTAS» (20 columnas)
# =============================================================================
def _consulta_row() -> dict:
    return {
        "fecha_consulta": "2026-10-05",
        "hora_consulta": "08:15",
        "turno": "mañana",
        "jerarquia": "Oficial",
        "personal_policial": "Pérez, Juan",
        "jefatura_regional": "Capital",
        "dependencias": "Comisaría 12",
        "tipo_consulta": "Antecedentes",
        "identificacion": "30.123.456",
        "tipo_arma_vehiculo": "Arma de fuego",
        "resultado": "Aprehensión",
        "causas_penales": "Robo agravado",
        "registro_legajo": "LEG-001",
        "autoridad_judicial": "Juzgado 3",
        "sistema_utilizado": "SIFCOP",
        "tramite_devuelto": "No",
        "hora_resp": "08:17",
        "personal_que_informa": "Gómez, Ana",
        "cargo": "Cabo",
        "operativos_preventivos": "Operativo Norte",
    }


def test_consultas_section_is_optional_and_normalized() -> None:
    body = _ingest_body()
    validated = validate_snapshot(body)
    assert validated.payload["consultas"] == []

    body["payload"]["consultas"] = [_consulta_row()]
    validated = validate_snapshot(body)
    assert len(validated.payload["consultas"]) == 1
    row = validated.payload["consultas"][0]
    assert row["turno"] == "MAÑANA"  # canonizado a mayúsculas
    assert row["fecha_consulta"] == "2026-10-05"
    assert row["resultado"] == "Aprehensión"
    assert validated.rejections == ()


def test_consulta_date_accepts_es_cl_dd_mm_yyyy() -> None:
    body = _ingest_body()
    row = _consulta_row()
    row["fecha_consulta"] = "05/10/2026"
    body["payload"]["consultas"] = [row]
    validated = validate_snapshot(body)
    assert validated.payload["consultas"][0]["fecha_consulta"] == "2026-10-05"


def test_invalid_consulta_row_is_rejected_without_failing_snapshot() -> None:
    body = _ingest_body()
    invalid = _consulta_row()
    invalid.pop("fecha_consulta")
    ok = _consulta_row()
    ok["resultado"] = "Negativo"
    body["payload"]["consultas"] = [invalid, ok]

    validated = validate_snapshot(body)

    assert "rejected_invalid_consulta" in validated.rejected_codes
    assert len(validated.payload["consultas"]) == 1
    assert validated.payload["consultas"][0]["resultado"] == "Negativo"
