"""Tests de extracción de métricas del workbook de la Policía (``EXCEL_POLICIA_URL``).

Construye un ``.xlsx`` sintético en memoria (con las mismas hojas/columnas que
el documento real) y verifica que ``parse_workbook`` emita el contrato del
endpoint ``GET /api/estadisticas``: series ``{name, value}``, ``NaN`` → 0,
claves ausentes → ``[]`` y comparativas semanales/mensuales.

Opcionalmente prueba contra el workbook real si ``EXCEL_POLICIA_TEST_NETWORK=1``.

    py backend/tests/test_estadisticas_excel_policia.py
    pytest backend/tests/test_estadisticas_excel_policia.py
"""

from __future__ import annotations

import datetime as dt
import io
import json
import os
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import pandas as pd  # noqa: E402
import pytest  # noqa: E402
from app.services import excel_policia  # noqa: E402

REAL_URL = os.environ.get(
    "EXCEL_POLICIA_URL",
    "https://docs.google.com/spreadsheets/d/174xdM9ckCBIuWU8EyK3BlJbX0xOfLjPlZmWgf4hHZao/export?format=xlsx",
)


def _xlsx_bytes() -> bytes:
    dashboard = pd.DataFrame(
        [
            [
                "REGIONAL",
                "TOTAL CONSULTAS",
                None,
                "DEPENDENCIA",
                "TOTAL CONSULTAS",
                None,
                "RESULTADO",
                "CANTIDAD",
            ],
            ["IRO", 1, None, "DEST. TERMINAL", 60, None, "NEGATIVO", 337],
            ["URC", 267, None, "CRIA 13", 47, None, "POSITIVO", 28],
            [None, float("nan"), None, "CRIA 9", 30, None, None, float("nan")],
        ]
    )
    consultas = pd.DataFrame(
        [
            ["TÍTULO", None, None, None, None, None, None, None, None],
            [
                "DIA",
                "HORA",
                "JERARQUIA",
                "PERSONAL POLICIAL DEPENDENCIAS",
                "DEPENDENCIAS",
                "REGIONAL, UUEE",
                "CONSULTA (PERSONA VEHICULO, ARMA)",
                "ID",
                "RESULTADO  (POSITIVO-NEVATIVO)",
            ],
            [None, None, None, "AGOSTO", None, None, None, None, None],
            [
                dt.date(2026, 8, 15),
                dt.time(21, 0),
                "SUBCRIO",
                "ALIMAFU",
                "CRIA YERBA BUENA",
                "URN",
                "PERSONA",
                1,
                "NEGATIVO",
            ],
            [
                dt.date(2026, 8, 16),
                dt.time(10, 30),
                "OF PPAL",
                "PALMAS",
                "CRIA 13",
                "URC",
                "PERSONA",
                2,
                "NEGATIVO",
            ],
            [
                dt.date(2026, 8, 17),
                dt.time(15, 45),
                "OFICIAL",
                "SORIA",
                "CRIA 14",
                "URC",
                "VEHICULO",
                3,
                "POSITIVO",
            ],
            [
                dt.date(2026, 8, 18),
                dt.time(23, 10),
                "CRIO",
                "GOMEZ",
                "CRIA 9",
                "URC",
                "PERSONA",
                4,
                "POSITIVO",
            ],
        ]
    )
    data = pd.DataFrame(
        [
            ["Mes", "Semana", "Desde", "Hasta", "Cantidad"],
            ["Agosto", "semana 1", dt.date(2026, 8, 15), dt.date(2026, 8, 21), 45],
            ["Agosto", "semana 2", dt.date(2026, 8, 22), dt.date(2026, 8, 28), 53],
            ["Septiembre", "semana 1", dt.date(2026, 9, 1), dt.date(2026, 9, 7), 81],
        ]
    )
    estadisticas = pd.DataFrame(
        [
            [None, None, None, None],
            [None, "Seleccionar Mes:", "SEPTIEMBRE", None],
            [None, None, None, None],
            [None, "Total del Mes:", 252, "Total General:", 364],
        ]
    )
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        dashboard.to_excel(writer, sheet_name="DASHBOARD_WEB", header=False, index=False)
        consultas.to_excel(writer, sheet_name="CONSULTAS", header=False, index=False)
        data.to_excel(writer, sheet_name="Data", header=False, index=False)
        estadisticas.to_excel(writer, sheet_name="ESTADISTICAS", header=False, index=False)
    return buffer.getvalue()


# =============================================================================
# URL de descarga
# =============================================================================
def test_to_export_url() -> None:
    base = "https://docs.google.com/spreadsheets/d/ABC123"
    assert excel_policia.to_export_url(f"{base}/edit?usp=sharing") == f"{base}/export?format=xlsx"
    assert (
        excel_policia.to_export_url(f"{base}/edit#gid=123") == f"{base}/export?format=xlsx&gid=123"
    )
    assert excel_policia.to_export_url(f"{base}/export?format=xlsx") == f"{base}/export?format=xlsx"
    for invalid in ("", "https://example.com/foo"):
        try:
            excel_policia.to_export_url(invalid)
        except ValueError:
            continue
        raise AssertionError(f"se esperaba ValueError para {invalid!r}")


# =============================================================================
# Parseo del workbook
# =============================================================================
def test_parse_contract() -> None:
    result = excel_policia.parse_workbook(_xlsx_bytes())

    # Contrato histórico: siglas regionales traducidas y dependencias limpias.
    # "IRO" se excluye; "CRIA X" → "Comisaría X" (con el mapeo estricto de 9).
    assert result["grafico_regionales"] == [
        {"name": "Unidad Regional Capital", "value": 267},
    ]
    # «Intervenciones por Unidad» ahora es el CONTEO REAL por rango derivado de
    # CONSULTAS (no el snapshot pre-agregado de DASHBOARD_WEB).
    assert result["intervenciones_por_unidad"] == result["incidentes_por_regional"]
    assert result["intervenciones_por_unidad"] == [
        {"name": "Unidad Regional Capital", "value": 3},
        {"name": "Unidad Regional Norte", "value": 1},
    ]
    # Lista única/ordenada de Unidades Regionales presentes (para selectores).
    assert result["regionales_disponibles"] == [
        "Unidad Regional Capital",
        "Unidad Regional Norte",
    ]
    assert result["dependencias_disponibles"] == [
        "Comisaría 13",
        "Comisaría 14",
        "Comisaría Novena 9°",
        "Comisaría YERBA BUENA",
    ]
    assert result["consultas_por_dependencia"] == result["grafico_dependencias"]
    assert result["grafico_dependencias"] == [
        {"name": "DEST. TERMINAL", "value": 60},
        {"name": "Comisaría 13", "value": 47},
        {"name": "Comisaría Novena 9°", "value": 30},
    ]
    assert result["alertas_resultados"] == [
        {"name": "NEGATIVO", "value": 337},
        {"name": "POSITIVO", "value": 28},
    ]

    # Evolución ESTRICTA por día (columna Fecha): un punto por día, en orden
    # cronológico y sin días nulos/sin fecha. Ya no hay agrupación global por turno.
    assert result["incidentes_por_fecha"] == [
        {"fecha": "15/08", "total": 1},
        {"fecha": "16/08", "total": 1},
        {"fecha": "17/08", "total": 1},
        {"fecha": "18/08", "total": 1},
    ]
    assert result["incidentes_por_dia"] == [
        {"name": "2026-08-15", "value": 1},
        {"name": "2026-08-16", "value": 1},
        {"name": "2026-08-17", "value": 1},
        {"name": "2026-08-18", "value": 1},
    ]
    assert result["incidentes_por_hora"] == [
        {"name": "10:00", "value": 1},
        {"name": "15:00", "value": 1},
        {"name": "21:00", "value": 1},
        {"name": "23:00", "value": 1},
    ]
    assert {item["name"] for item in result["incidentes_por_tipo"]} == {"PERSONA", "VEHICULO"}
    assert result["incidentes_por_regional"] == [
        {"name": "Unidad Regional Capital", "value": 3},
        {"name": "Unidad Regional Norte", "value": 1},
    ]
    assert result["incidentes_por_dependencia"][0] == {"name": "Comisaría 13", "value": 1}

    # Ranking Top 5 (orden desc; empate → nombre) y turnos por día. Cada ítem
    # incluye la variación real (sin período anterior → pct None, nunca 0).
    assert result["rankingTop5"] == [
        {
            "name": "Comisaría 13",
            "intervenciones": 1,
            "value": 1,
            "variacion_abs": 1,
            "variacion_pct": None,
        },
        {
            "name": "Comisaría 14",
            "intervenciones": 1,
            "value": 1,
            "variacion_abs": 1,
            "variacion_pct": None,
        },
        {
            "name": "Comisaría Novena 9°",
            "intervenciones": 1,
            "value": 1,
            "variacion_abs": 1,
            "variacion_pct": None,
        },
        {
            "name": "Comisaría YERBA BUENA",
            "intervenciones": 1,
            "value": 1,
            "variacion_abs": 1,
            "variacion_pct": None,
        },
    ]
    assert len(result["rankingTop5"]) <= 5
    assert result["incidentes_turno_por_dia"] == [
        {"fecha": "15/08", "mañana": 0, "tarde": 1, "noche": 0},
        {"fecha": "16/08", "mañana": 1, "tarde": 0, "noche": 0},
        {"fecha": "17/08", "mañana": 0, "tarde": 1, "noche": 0},
        {"fecha": "18/08", "mañana": 0, "tarde": 0, "noche": 1},
    ]

    # Meses y KPIs reales.
    assert result["por_mes"] == [
        {
            "mes": "2026-08",
            "total_consultas": 4,
            "aprehendidos": 1,
            "vehiculos": 1,
            "armas": 0,
        }
    ]
    assert result["consultas_por_mes"] == [{"name": "2026-08", "value": 4}]

    # Logística: el subconjunto de VEHICULO/ARMA se aísla correctamente y se
    # expone por Unidad Regional + alias camelCase sin nulos.
    assert result["logistica_vehiculos_por_regional"] == [
        {"name": "Unidad Regional Capital", "value": 1}
    ]
    assert result["logistica_vehiculos_por_dependencia"] == [{"name": "Comisaría 14", "value": 1}]
    assert result["logistica_armas_por_regional"] == []
    assert result["logistica_armas_por_dependencia"] == []
    assert result["vehiculosPorRegional"] == result["logistica_vehiculos_por_regional"]
    assert result["armasPorRegional"] == result["logistica_armas_por_regional"]

    # Comparativas semanales/mensuales.
    assert result["comparativas_semanales"] == [
        {"name": "Agosto semana 1", "value": 45},
        {"name": "Agosto semana 2", "value": 53},
        {"name": "Septiembre semana 1", "value": 81},
    ]
    assert {item["name"]: item["value"] for item in result["comparativas_mensuales"]} == {
        "Agosto": 98,
        "Septiembre": 81,
    }

    # KPIs y totales (incluye aprehendidos derivado de PERSONA + POSITIVO).
    assert result["kpis"] == {
        "total_consultas": 4,
        "aprehendidos": 1,
        "personas": 3,
        "vehiculos": 1,
        "armas": 0,
        "positivos": 2,
        "negativos": 2,
    }
    assert result["totales"] == {
        "total_consultas": 4,
        "aprehendidos": 1,
        "vehiculos_secuestrados": 1,
        "armas_secuestradas": 0,
    }
    assert result["estadisticas_totales"] == {"total_mes": 252, "total_general": 364}

    # Sin NaN/Inf: el JSON es serializable de forma estricta.
    json.dumps(result, allow_nan=False, ensure_ascii=False)


def test_missing_sheets_are_empty() -> None:
    buffer = io.BytesIO()
    pd.DataFrame([["x", 1]]).to_excel(buffer, sheet_name="Otra", header=False, index=False)
    result = excel_policia.parse_workbook(buffer.getvalue())
    for key in (
        "grafico_regionales",
        "grafico_dependencias",
        "alertas_resultados",
        "intervenciones_por_unidad",
        "consultas_por_dependencia",
        "incidentes_por_fecha",
        "incidentes_por_dia",
        "incidentes_por_tipo",
        "incidentes_por_regional",
        "incidentes_por_dependencia",
        "incidentes_por_resultado",
        "distribucion_incidentes",
        "logistica_vehiculos_por_regional",
        "logistica_vehiculos_por_dependencia",
        "logistica_armas_por_regional",
        "logistica_armas_por_dependencia",
        "vehiculosPorRegional",
        "armasPorRegional",
        "por_mes",
        "consultas_por_mes",
        "rankingTop5",
        "regionales_disponibles",
        "dependencias_disponibles",
        "incidentes_turno_por_dia",
        "comparativas",
    ):
        assert result[key] == []
    assert result["kpis"]["total_consultas"] == 0
    assert result["kpis"]["aprehendidos"] == 0
    assert result["totales"] == {
        "total_consultas": 0,
        "aprehendidos": 0,
        "vehiculos_secuestrados": 0,
        "armas_secuestradas": 0,
    }


# =============================================================================
# Traducción de regionales
# =============================================================================
def test_translate_regional() -> None:
    expected = {
        "URN": "Unidad Regional Norte",
        "URS": "Unidad Regional Sur",
        "URE": "Unidad Regional Este",
        "URO": "Unidad Regional Oeste",
        "URC": "Unidad Regional Capital",
    }
    for sigla, nombre in expected.items():
        assert excel_policia._translate_regional(sigla) == nombre
        # Tolerante a minúsculas, espacios y acentos no aplica a las siglas.
        assert excel_policia._translate_regional(f"  {sigla.lower()} ") == nombre
    # Valores desconocidos se preservan tal cual (p. ej. IRO).
    assert excel_policia._translate_regional("IRO") == "IRO"
    assert excel_policia._translate_regional("  iro ") == "iro"
    assert excel_policia._translate_regional(None) == ""
    assert excel_policia._translate_regional(float("nan")) == ""
    # Dos formas que mapean al mismo nombre se suman (agrupación por traducido).
    merged = excel_policia._translate_series(
        [
            {"name": "URC", "value": 2},
            {"name": "Unidad Regional Capital", "value": 3},
        ]
    )
    assert merged == [{"name": "Unidad Regional Capital", "value": 5}]


# =============================================================================
# Filtrado de turnos vacíos (columna TURNO dedicada)
# =============================================================================
def _consultas_con_turno() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ["DIA", "HORA", "TURNO", "DEPENDENCIAS", "REGIONAL, UUEE", "CONSULTA", "RESULTADO"],
            [dt.date(2026, 8, 15), dt.time(8, 0), "MAÑANA", "DEP A", "URN", "PERSONA", "NEGATIVO"],
            [
                dt.date(2026, 8, 15),
                dt.time(9, 0),
                " mañana ",
                "DEP B",
                "URS",
                "VEHICULO",
                "POSITIVO",
            ],
            [dt.date(2026, 8, 15), dt.time(15, 0), "TARDE", "DEP A", "URE", "PERSONA", "NEGATIVO"],
            [dt.date(2026, 8, 15), dt.time(15, 30), "", "DEP C", "URO", "PERSONA", "POSITIVO"],
            [
                dt.date(2026, 8, 15),
                dt.time(16, 0),
                float("nan"),
                "DEP D",
                "URC",
                "PERSONA",
                "NEGATIVO",
            ],
            [
                dt.date(2026, 8, 15),
                dt.time(17, 0),
                "DESCONOCIDO",
                "DEP E",
                "IRO",
                "ARMA",
                "POSITIVO",
            ],
        ]
    )


def test_turnos_vacios_se_excluyen() -> None:
    series = excel_policia._consultas_series(_consultas_con_turno())
    # Sólo MAÑANA y TARDE; las filas con turno vacío/NaN/desconocido no suman.
    assert series["incidentes_turno_por_dia"] == [
        {"fecha": "15/08", "mañana": 2, "tarde": 1, "noche": 0},
    ]
    # La evolución diaria cuenta TODAS las filas con fecha válida (turno aparte).
    assert series["incidentes_por_fecha"] == [{"fecha": "15/08", "total": 6}]
    # El resto de series sigue agregando todas las filas temporalmente válidas.
    assert series["kpis"]["total_consultas"] == 6


def test_regionales_traducidos_en_consultas() -> None:
    series = excel_policia._consultas_series(_consultas_con_turno())
    nombres = {item["name"] for item in series["incidentes_por_regional"]}
    # "IRO" (basura) ya NO aparece; las siglas válidas se traducen.
    assert nombres == {
        "Unidad Regional Norte",
        "Unidad Regional Sur",
        "Unidad Regional Este",
        "Unidad Regional Oeste",
        "Unidad Regional Capital",
    }
    assert "IRO" not in nombres
    assert "URN" not in nombres and "URC" not in nombres


def test_vehiculos_y_armas_por_regional() -> None:
    frame = pd.DataFrame(
        [
            ["DIA", "TURNO", "DEPENDENCIAS", "REGIONAL, UUEE", "CONSULTA", "RESULTADO"],
            [dt.date(2026, 9, 1), "MAÑANA", "DEP A", "URN", "VEHICULO", "POSITIVO"],
            [dt.date(2026, 9, 1), "TARDE", "DEP B", "URS", "VEHICULO", "POSITIVO"],
            [dt.date(2026, 9, 1), "NOCHE", "DEP C", "IRO", "VEHICULO", "NEGATIVO"],
            [dt.date(2026, 9, 1), "MAÑANA", "DEP D", None, "VEHICULO", "NEGATIVO"],
            [dt.date(2026, 9, 2), "MAÑANA", "DEP E", "URC", "ARMA", "POSITIVO"],
            [dt.date(2026, 9, 2), "TARDE", "DEP F", "URN", "ARMA", "POSITIVO"],
            [dt.date(2026, 9, 2), "NOCHE", "DEP G", "COP", "ARMA", "NEGATIVO"],
            [dt.date(2026, 9, 3), "MAÑANA", "DEP H", None, "ARMA", "NEGATIVO"],
        ]
    )
    series = excel_policia._consultas_series(frame)
    # Vehículos y armas por Unidad Regional: siglas traducidas, sin IRO/COP/nulos.
    assert series["logistica_vehiculos_por_regional"] == [
        {"name": "Unidad Regional Norte", "value": 1},
        {"name": "Unidad Regional Sur", "value": 1},
    ]
    assert series["logistica_armas_por_regional"] == [
        {"name": "Unidad Regional Capital", "value": 1},
        {"name": "Unidad Regional Norte", "value": 1},
    ]
    nombres = {
        item["name"]
        for item in (
            series["logistica_vehiculos_por_regional"] + series["logistica_armas_por_regional"]
        )
    }
    assert {"IRO", "COP"} & nombres == set()
    # Evolución diaria estricta, cronológica y sin días nulos.
    assert series["incidentes_por_fecha"] == [
        {"fecha": "01/09", "total": 4},
        {"fecha": "02/09", "total": 3},
        {"fecha": "03/09", "total": 1},
    ]


# =============================================================================
# Diccionario de siglas, exclusiones de basura y fechas
# =============================================================================
def test_clean_dependencia_y_exclusiones() -> None:
    # Mapeo estricto + prefijo genérico.
    assert excel_policia._clean_dependencia("CRIA 9") == "Comisaría Novena 9°"
    assert excel_policia._clean_dependencia("cria 9") == "Comisaría Novena 9°"
    assert excel_policia._clean_dependencia("CRIA 13") == "Comisaría 13"
    assert excel_policia._clean_dependencia("CRIA YERBA BUENA") == "Comisaría YERBA BUENA"
    assert excel_policia._clean_dependencia("DEST. TERMINAL") == "DEST. TERMINAL"
    assert excel_policia._clean_dependencia(None) == ""
    assert excel_policia._clean_dependencia(float("nan")) == ""
    # Exclusiones por `_normalize`.
    for basura in ("IRO", "iro", "COP", "cop", "REGIONAL, UUEE", "regional, uuee "):
        assert excel_policia._is_excluded_geo(basura) is True
    for valido in ("URC", "CRIA 9", "DEST. TERMINAL"):
        assert excel_policia._is_excluded_geo(valido) is False
    assert excel_policia._is_excluded_geo(None) is True
    assert excel_policia._is_excluded_geo(float("nan")) is True


def test_date_helpers() -> None:
    assert excel_policia._date_of("15/08/2026") == dt.date(2026, 8, 15)
    assert excel_policia._date_of("15-08-2026") == dt.date(2026, 8, 15)
    assert excel_policia._date_of("2026/08/15") == dt.date(2026, 8, 15)
    assert excel_policia._date_of("2026-08-15 00:00:00") == dt.date(2026, 8, 15)
    assert excel_policia._month_of("01/09/2026") == "2026-09"
    assert excel_policia._daymonth_of(dt.date(2026, 9, 1)) == "01/09"
    assert excel_policia._date_of("sin fecha") is None
    assert excel_policia._month_of(None) is None
    assert excel_policia._daymonth_of(float("nan")) is None


# =============================================================================
# Ranking Top 5 (máx 5, orden desc) y turnos por día
# =============================================================================
def _consultas_exclusiones() -> pd.DataFrame:
    return pd.DataFrame(
        [
            ["DIA", "TURNO", "DEPENDENCIAS", "REGIONAL, UUEE", "CONSULTA", "RESULTADO"],
            [dt.date(2026, 8, 31), "NOCHE", "CRIA 9", "URC", "PERSONA", "POSITIVO"],
            [dt.date(2026, 8, 31), "NOCHE", "CRIA 9", "URC", "PERSONA", "POSITIVO"],
            [dt.date(2026, 9, 1), "MAÑANA", "IRO", "IRO", "PERSONA", "POSITIVO"],
            [dt.date(2026, 9, 1), "TARDE", "COP", "COP", "VEHICULO", "NEGATIVO"],
            [
                dt.date(2026, 9, 1),
                "NOCHE",
                "REGIONAL, UUEE",
                "REGIONAL, UUEE",
                "ARMA",
                "NEGATIVO",
            ],
            [dt.date(2026, 9, 2), "MAÑANA", None, None, "PERSONA", "NEGATIVO"],
            [dt.date(2026, 9, 2), "TARDE", "CRIA 13", "URC", "VEHICULO", "POSITIVO"],
            [dt.date(2026, 9, 2), "TARDE", "CRIA 12", "URC", "PERSONA", "NEGATIVO"],
            [dt.date(2026, 9, 3), "MAÑANA", "CRIA 11", "URN", "PERSONA", "NEGATIVO"],
            [dt.date(2026, 9, 3), "MAÑANA", "CRIA 10", "URN", "PERSONA", "NEGATIVO"],
            [dt.date(2026, 9, 3), "TARDE", "CRIA 14", "URE", "PERSONA", "NEGATIVO"],
            [dt.date(2026, 9, 4), "NOCHE", "CRIA 15", "URO", "PERSONA", "POSITIVO"],
        ]
    )


def test_ranking_top5_maximo_y_orden() -> None:
    series = excel_policia._consultas_series(_consultas_exclusiones())
    ranking = series["rankingTop5"]
    assert len(ranking) == 5
    assert ranking[0] == {
        "name": "Comisaría Novena 9°",
        "intervenciones": 2,
        "value": 2,
        "variacion_abs": 2,
        "variacion_pct": None,
    }
    valores = [item["intervenciones"] for item in ranking]
    assert valores == sorted(valores, reverse=True)
    # Sin ventana anterior con datos, la variación porcentual es None (no 0).
    assert all(item["value"] == item["intervenciones"] for item in ranking)
    assert all(item["variacion_pct"] is None for item in ranking)
    # Hay 7 dependencias reales; el ranking se corta a 5 y excluye la basura.
    nombres = {item["name"] for item in series["incidentes_por_dependencia"]}
    assert nombres == {
        "Comisaría Novena 9°",
        "Comisaría 10",
        "Comisaría 11",
        "Comisaría 12",
        "Comisaría 13",
        "Comisaría 14",
        "Comisaría 15",
    }
    assert {"IRO", "COP", "REGIONAL, UUEE"} & nombres == set()


def test_turno_por_dia_y_exclusion_geografica() -> None:
    series = excel_policia._consultas_series(_consultas_exclusiones())
    assert series["incidentes_turno_por_dia"] == [
        {"fecha": "31/08", "mañana": 0, "tarde": 0, "noche": 2},
        {"fecha": "01/09", "mañana": 1, "tarde": 1, "noche": 1},
        {"fecha": "02/09", "mañana": 1, "tarde": 2, "noche": 0},
        {"fecha": "03/09", "mañana": 2, "tarde": 1, "noche": 0},
        {"fecha": "04/09", "mañana": 0, "tarde": 0, "noche": 1},
    ]
    # Las regionales basura no aparecen; las válidas sí.
    regionales = {item["name"] for item in series["incidentes_por_regional"]}
    assert regionales == {
        "Unidad Regional Capital",
        "Unidad Regional Norte",
        "Unidad Regional Este",
        "Unidad Regional Oeste",
    }
    # La exclusión geográfica NO descarta la consulta de los totales.
    assert series["kpis"]["total_consultas"] == 12


def test_por_mes_y_consultas_por_mes() -> None:
    series = excel_policia._consultas_series(_consultas_exclusiones())
    assert series["por_mes"] == [
        {
            "mes": "2026-08",
            "total_consultas": 2,
            "aprehendidos": 2,
            "vehiculos": 0,
            "armas": 0,
        },
        {
            "mes": "2026-09",
            "total_consultas": 10,
            "aprehendidos": 2,
            "vehiculos": 2,
            "armas": 1,
        },
    ]
    assert series["consultas_por_mes"] == [
        {"name": "2026-08", "value": 2},
        {"name": "2026-09", "value": 10},
    ]


# =============================================================================
# Filtro temporal por `rango` + variaciones del ranking
# =============================================================================
def _consultas_temporales() -> pd.DataFrame:
    """Frame con ventana anterior (28/08–03/09) y actual (04/09–10/09)."""
    return pd.DataFrame(
        [
            ["DIA", "TURNO", "DEPENDENCIAS", "REGIONAL, UUEE", "CONSULTA", "RESULTADO"],
            # Ventana ANTERIOR de `semana` con anchor 2026-09-10.
            [dt.date(2026, 8, 29), "MAÑANA", "CRIA 13", "URC", "PERSONA", "POSITIVO"],
            [dt.date(2026, 8, 30), "TARDE", "CRIA 13", "URC", "PERSONA", "POSITIVO"],
            # Ventana ACTUAL.
            [dt.date(2026, 9, 5), "MAÑANA", "CRIA 13", "URC", "PERSONA", "POSITIVO"],
            [dt.date(2026, 9, 6), "TARDE", "CRIA 13", "URC", "VEHICULO", "NEGATIVO"],
            [dt.date(2026, 9, 7), "NOCHE", "CRIA 13", "URC", "PERSONA", "POSITIVO"],
            [dt.date(2026, 9, 8), "MAÑANA", "CRIA 14", "URN", "PERSONA", "NEGATIVO"],
            # Fuera de ambas ventanas (rango=semana la excluye).
            [dt.date(2026, 1, 1), "MAÑANA", "CRIA 9", "URS", "PERSONA", "NEGATIVO"],
        ]
    )


def test_rango_dias_helpers() -> None:
    assert excel_policia._rango_dias("ayer") == 1
    assert excel_policia._rango_dias("semana") == 7
    assert excel_policia._rango_dias("mes") == 30
    assert excel_policia._rango_dias("anio") == 365
    assert excel_policia._rango_dias("todo") is None
    assert excel_policia._rango_dias("all") is None
    # Falta o inválido → default seguro.
    assert excel_policia._rango_dias(None) == 365
    assert excel_policia._rango_dias("desconocido") == 365


def test_filtro_por_rango_semana_excluye_antiguas() -> None:
    frame = _consultas_temporales()
    semana = excel_policia._consultas_series(frame, rango="semana")
    dependencias = {item["name"] for item in semana["incidentes_por_dependencia"]}
    assert dependencias == {"Comisaría 13", "Comisaría 14"}
    assert "Comisaría Novena 9°" not in dependencias
    assert semana["kpis"]["total_consultas"] == 4
    # Sin filtro (todo) también entra la fila antigua.
    todo = excel_policia._consultas_series(frame, rango="todo")
    assert todo["kpis"]["total_consultas"] == 7


def test_regionales_disponibles_unicas_y_traducidas() -> None:
    series = excel_policia._consultas_series(_consultas_con_turno())
    disponibles = series["regionales_disponibles"]
    assert disponibles == [
        "Unidad Regional Capital",
        "Unidad Regional Este",
        "Unidad Regional Norte",
        "Unidad Regional Oeste",
        "Unidad Regional Sur",
    ]
    assert "IRO" not in disponibles
    assert disponibles == sorted(set(disponibles))


def test_ranking_variaciones_actual_vs_anterior() -> None:
    ranking = excel_policia._consultas_series(_consultas_temporales(), rango="semana")[
        "rankingTop5"
    ]
    por_nombre = {item["name"]: item for item in ranking}
    trece = por_nombre["Comisaría 13"]
    assert trece["intervenciones"] == 3
    assert trece["value"] == 3
    assert trece["variacion_abs"] == 1  # 3 actual − 2 anterior
    assert trece["variacion_pct"] == 50.0
    catorce = por_nombre["Comisaría 14"]
    assert catorce["intervenciones"] == 1
    assert catorce["variacion_abs"] == 1
    assert catorce["variacion_pct"] is None  # sin base anterior: nunca 0
    assert ranking[0]["name"] == "Comisaría 13"


def test_aprehendidos_desde_hoja_positivos() -> None:
    # Si el workbook trae la hoja `Positivos`, su total global manda.
    buffer = io.BytesIO()
    dashboard = pd.DataFrame([["REGIONAL", "TOTAL"], ["URC", 10]])
    consultas = pd.DataFrame(
        [
            ["DIA", "TURNO", "DEPENDENCIAS", "REGIONAL, UUEE", "CONSULTA", "RESULTADO"],
            [dt.date(2026, 9, 1), "MAÑANA", "CRIA 9", "URC", "PERSONA", "POSITIVO"],
        ]
    )
    positivos = pd.DataFrame([["POSITIVOS", 25]])
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        dashboard.to_excel(writer, sheet_name="DASHBOARD_WEB", header=False, index=False)
        consultas.to_excel(writer, sheet_name="CONSULTAS", header=False, index=False)
        positivos.to_excel(writer, sheet_name="Positivos", header=False, index=False)
    result = excel_policia.parse_workbook(buffer.getvalue())
    assert result["kpis"]["aprehendidos"] == 25
    assert result["totales"]["aprehendidos"] == 25
    json.dumps(result, allow_nan=False, ensure_ascii=False)


@pytest.mark.skipif(
    os.environ.get("EXCEL_POLICIA_TEST_NETWORK") != "1",
    reason="requiere red; exportá EXCEL_POLICIA_TEST_NETWORK=1",
)
def test_real_workbook_network() -> None:
    result = excel_policia.build_estadisticas(REAL_URL)
    assert result["grafico_regionales"], "el workbook real debe traer regionales"
    assert result["incidentes_por_fecha"], "el workbook real debe traer evolución diaria"
    json.dumps(result, allow_nan=False, ensure_ascii=False)


if __name__ == "__main__":
    test_to_export_url()
    test_parse_contract()
    test_missing_sheets_are_empty()
    test_translate_regional()
    test_turnos_vacios_se_excluyen()
    test_regionales_traducidos_en_consultas()
    test_vehiculos_y_armas_por_regional()
    test_clean_dependencia_y_exclusiones()
    test_date_helpers()
    test_ranking_top5_maximo_y_orden()
    test_turno_por_dia_y_exclusion_geografica()
    test_por_mes_y_consultas_por_mes()
    test_rango_dias_helpers()
    test_filtro_por_rango_semana_excluye_antiguas()
    test_regionales_disponibles_unicas_y_traducidas()
    test_ranking_variaciones_actual_vs_anterior()
    test_aprehendidos_desde_hoja_positivos()
    if os.environ.get("EXCEL_POLICIA_TEST_NETWORK") == "1":
        test_real_workbook_network()
    print("OK")
