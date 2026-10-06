"""Tests del endpoint de estadísticas de hospitales (Google Sheets).

Sirve un ``.xlsx`` sintético en memoria (mockeando la descarga) y verifica la
respuesta; además prueba la normalización de URLs de Google Sheets.

    py backend/tests/test_hospitales.py
    # o, con pytest:
    pytest backend/tests/test_hospitales.py
"""

from __future__ import annotations

import io
import re
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import pandas as pd  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api import hospitales  # noqa: E402
from app.core.errors import register_exception_handlers  # noqa: E402

HEADERS = [
    "Localidad",
    "Homicidios",
    "Lesiones\nCulposas",
    "Heridos con arma de fuego",
    "Violencia Familiar",
    "Femicidio",
]


def _xlsx_bytes() -> bytes:
    rows = [
        ["Ruido", "", "", "", "", ""],
        ["", "", "", "", "", ""],
        ["Informe hospitalario", "", "", "", "", ""],
        ["", "", "", "", "", ""],
        ["", "", "", "", "", ""],
        ["", "", "", "", "", ""],
        HEADERS,
        ["Centro", 3, 4, float("nan"), 2, 1],
        ["Norte", 0, 6, 4, float("nan"), 0],
        ["Totales", 30, 30, 30, 30, 30],
    ]
    buffer = io.BytesIO()
    pd.DataFrame(rows).to_excel(buffer, sheet_name="Datos", header=False, index=False)
    return buffer.getvalue()


def _client() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)
    app.include_router(hospitales.router, prefix="/api/hospitales")
    return TestClient(app)


def test_to_export_url() -> None:
    base = "https://docs.google.com/spreadsheets/d/ABC123"
    assert (
        hospitales.to_export_url(f"{base}/edit?usp=sharing")
        == f"{base}/export?format=xlsx"
    )
    assert (
        hospitales.to_export_url(f"{base}/edit#gid=123")
        == f"{base}/export?format=xlsx&gid=123"
    )
    assert (
        hospitales.to_export_url(f"{base}/export?format=xlsx")
        == f"{base}/export?format=xlsx"
    )
    for invalid in ("", "https://example.com/foo"):
        try:
            hospitales.to_export_url(invalid)
        except ValueError:
            continue
        raise AssertionError(f"se esperaba ValueError para {invalid!r}")


def _run_ok_case() -> None:
    previous_url = hospitales.SHEET_URL
    previous_download = hospitales._download_sheet
    hospitales.SHEET_URL = "https://docs.google.com/spreadsheets/d/ABC123/edit?usp=sharing"
    hospitales._download_sheet = lambda _url: _xlsx_bytes()
    try:
        response = _client().get("/api/hospitales/estadisticas")
    finally:
        hospitales.SHEET_URL = previous_url
        hospitales._download_sheet = previous_download

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["sheet"] == "Datos"
    assert data["total_rows"] == 2
    for header in HEADERS:
        cleaned = re.sub(r"\s+", " ", header).strip()
        assert cleaned in data["columns"]
    assert all("\n" not in column for column in data["columns"])
    assert "Lesiones Culposas" in data["columns"]

    first, second = data["rows"]
    # NaN/vacíos → 0.
    assert first["Heridos con arma de fuego"] == 0
    assert second["Violencia Familiar"] == 0
    assert first["Localidad"] == "Centro"
    assert first["Homicidios"] == 3
    assert second["Heridos con arma de fuego"] == 4

    # La fila "Totales" se excluye: sin doble suma en kpis/chartData.
    assert all(str(row.get("Localidad")).strip() != "Totales" for row in data["rows"])
    assert data["kpis"]["homicidios"] == 3
    assert data["kpis"]["lesiones_culposas"] == 10
    causes = {item["causa"]: item["cantidad"] for item in data["chartData"]}
    assert causes["Homicidios"] == 3
    # 4 + 6 de las filas de datos, NO 40 (con la fila Totales=30).
    assert causes["Lesiones Culposas"] == 10
    # chartData no incluye columnas en 0.
    assert all(item["cantidad"] > 0 for item in data["chartData"])


def _run_unconfigured_case() -> None:
    previous_url = hospitales.SHEET_URL
    hospitales.SHEET_URL = ""
    try:
        response = _client().get("/api/hospitales/estadisticas")
    finally:
        hospitales.SHEET_URL = previous_url
    assert response.status_code == 503, response.text
    error = response.json()["error"]
    assert error["code"] == "UNAVAILABLE"
    assert "configurada" in error["message"]


def test_hospitales_estadisticas() -> None:
    _run_ok_case()


def test_hospitales_unconfigured_url() -> None:
    _run_unconfigured_case()


if __name__ == "__main__":
    test_to_export_url()
    _run_ok_case()
    _run_unconfigured_case()
    print("OK")
