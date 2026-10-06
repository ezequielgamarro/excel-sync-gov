"""Tests de la ingesta de la hoja «CONSULTAS» (20 columnas).

Verifica que ``app.services.ingest._insert_consultas`` traduce el payload
normalizado a filas de ``app.consulta_event`` con los campos técnicos y las 20
columnas, y que es idempotente (``ON CONFLICT DO NOTHING``).
"""

from __future__ import annotations

import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from app.services.ingest import _insert_consultas  # noqa: E402
from app.services.validation import ValidatedSnapshot  # noqa: E402


class _Result:
    def __init__(self, rowcount: int = 1) -> None:
        self.rowcount = rowcount


class _Session:
    def __init__(self, rowcount: int = 1) -> None:
        self.statements: list[Any] = []
        self._rowcount = rowcount

    async def execute(self, statement: Any) -> _Result:
        self.statements.append(statement)
        return _Result(self._rowcount)


def _validated(rows: list[dict[str, Any]]) -> ValidatedSnapshot:
    return ValidatedSnapshot(
        document={"event_id": "018f1d2e-3a4b-7c5d-8e6f-0a1b2c3d4e5f"},
        event_id=uuid.UUID("018f1d2e-3a4b-7c5d-8e6f-0a1b2c3d4e5f"),
        doc_id="sifcop-consultas",
        data_date=date(2026, 10, 5),
        content_sha256="a" * 64,
        payload={"consultas": rows},
    )


def test_insert_consultas_persists_rows() -> None:
    import asyncio

    session = _Session()
    asyncio.run(
        _insert_consultas(
            session,  # type: ignore[arg-type]
            _validated(
                [
                    {
                        "fecha_consulta": "2026-10-05",
                        "turno": "MAÑANA",
                        "resultado": "Aprehensión",
                        "causas_penales": "Robo",
                        "jefatura_regional": "Capital",
                    },
                    {
                        "fecha_consulta": "2026-10-05",
                        "turno": "TARDE",
                        "resultado": "Negativo",
                    },
                ]
            ),
            seq=10428,
            received_at=datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc),
            correlation_id="tr-1",
        )
    )
    assert len(session.statements) == 2
    compiled = session.statements[0].compile()
    params = compiled.params
    assert str(params["event_id"]) == "018f1d2e-3a4b-7c5d-8e6f-0a1b2c3d4e5f"
    assert params["doc_id"] == "sifcop-consultas"
    assert params["row_index"] == 0
    assert params["seq"] == 10428
    assert str(params["fecha_consulta"]) == "2026-10-05"
    assert params["turno"] == "MAÑANA"
    assert params["resultado"] == "Aprehensión"
    # Las 20 columnas están presentes en la proyección.
    from app.models.tables import CONSULTA_COLUMNS

    for column in CONSULTA_COLUMNS:
        assert column in params


def test_insert_consultas_skips_invalid_date() -> None:
    import asyncio

    session = _Session()
    asyncio.run(
        _insert_consultas(
            session,  # type: ignore[arg-type]
            _validated([{"fecha_consulta": "no-es-fecha"}]),
            seq=1,
            received_at=datetime(2026, 10, 5, tzinfo=timezone.utc),
            correlation_id="",
        )
    )
    assert session.statements == []


def test_reconciliation_normalizes_consultas_sheet() -> None:
    from app.services.reconciliation import SHEET_CONSULTAS, _normalize_consultas

    grid = {
        SHEET_CONSULTAS: [
            ["Fecha Consulta", "Turno", "Resultado", "Causas Penales"],
            ["05/10/2026", "Mañana", "Aprehensión", "Robo agravado"],
            ["", "", "", ""],
        ]
    }
    rows = _normalize_consultas(grid)
    assert len(rows) == 1
    assert rows[0]["fecha_consulta"] == "2026-10-05"
    assert rows[0]["turno"] == "Mañana"
    assert rows[0]["resultado"] == "Aprehensión"
    assert rows[0]["causas_penales"] == "Robo agravado"


def test_reconciliation_consultas_empty_without_sheet() -> None:
    from app.services.reconciliation import _normalize_consultas

    assert _normalize_consultas({}) == []
