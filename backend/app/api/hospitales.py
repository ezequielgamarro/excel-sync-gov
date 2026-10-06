"""Estadísticas de la planilla de hospitales (Google Sheets).

Descarga la planilla desde un enlace de Google Sheets, lee su **primera pestaña**,
detecta el cuadro numérico que empieza en la fila 7 y devuelve JSON estructurado.
Los ``NaN``/vacíos se normalizan a 0; la primera columna se mantiene como texto.

La URL se configura en ``SHEET_URL`` (o por entorno ``HOSPITALES_SHEET_URL``).
``httpx``/``pandas``/``openpyxl`` se importan de forma **perezosa**.
"""

from __future__ import annotations

import io
import json
import math
import os
import re
from typing import Any

from fastapi import APIRouter
from starlette.responses import JSONResponse

from app.core.errors import raise_http_error

router = APIRouter(tags=["Hospitales"])

#: Enlace de Google Sheets a leer. Pegá aquí el enlace del usuario, o definí la
#: variable de entorno ``HOSPITALES_SHEET_URL``.
SHEET_URL = os.environ.get("HOSPITALES_SHEET_URL", "")

#: Fila (índice 0-based) desde la que se busca el encabezado del cuadro.
HEADER_SCAN_START = 5
#: Columnas clave que debe contener la fila de encabezado (al menos 2).
HEADER_MIN_MATCHES = 2
KEY_COLUMNS = (
    "homicidios",
    "lesiones culposas",
    "heridos con arma de fuego",
    "violencia familiar",
    "femicidio",
)

_ACCENT_MAP = str.maketrans("áéíóúüñÁÉÍÓÚÜÑ", "aeiouunAEIOUUN")
_SHEET_ID_RE = re.compile(r"/spreadsheets/d/([a-zA-Z0-9_-]+)")
_GID_RE = re.compile(r"[#?&]gid=(\d+)")


def _normalize(value: Any) -> str:
    text = str(value).translate(_ACCENT_MAP).strip().lower()
    return " ".join(text.split())


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return str(value).strip().lower() in ("", "nan", "none", "nat")


def _is_total_row(values: list[Any]) -> bool:
    """``True`` si la fila es un total (p. ej. "Totales") en su primera columna."""
    if not values:
        return False
    first = _normalize(values[0])
    return first in ("total", "totales", "total general") or first.startswith("total")


def _clean_name(value: Any) -> str:
    """Colapsa saltos de línea/espacios múltiples y recorta."""
    return re.sub(r"\s+", " ", str(value)).strip()


def _to_float(value: Any) -> float | None:
    """Convierte una celda a ``float``; no numérica/NaN → ``None``."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        return float(str(value).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None


def _looks_like_grand_total(rows: list[list[Any]]) -> bool:
    """Heurística: última fila sin etiqueta cuyas celdas igualan los subtotales."""
    if len(rows) < 2 or not _is_empty(rows[-1][0]):
        return False
    last = rows[-1]
    previous = rows[:-1]
    width = max((len(row) for row in rows), default=0)
    matched = False
    for index in range(1, width):
        value = _to_float(last[index]) if index < len(last) else None
        if value is None:
            continue
        column_sum = 0.0
        for row in previous:
            cell = _to_float(row[index]) if index < len(row) else None
            if cell is not None:
                column_sum += cell
        if abs(value - column_sum) > 0.5:
            return False
        matched = True
    return matched


def to_export_url(url: str) -> str:
    """Convierte un enlace de Google Sheets en URL de descarga directa ``.xlsx``.

    - ``.../edit?usp=sharing`` → ``.../export?format=xlsx``
    - ``.../edit#gid=123`` → ``.../export?format=xlsx&gid=123``
    - Si ya es ``.../export?format=xlsx`` se devuelve normalizada.

    Lanza ``ValueError`` si la URL no es válida o no se reconoce.
    """
    candidate = (url or "").strip()
    if not candidate:
        raise ValueError("La URL de Google Sheets no es válida (está vacía).")
    match = _SHEET_ID_RE.search(candidate)
    if not match:
        raise ValueError("La URL de Google Sheets no es válida (falta el ID del documento).")
    export = f"https://docs.google.com/spreadsheets/d/{match.group(1)}/export?format=xlsx"
    gid = _GID_RE.search(candidate)
    if gid:
        export += f"&gid={gid.group(1)}"
    return export


def _download_sheet(export_url: str) -> bytes:
    """Descarga el contenido ``.xlsx`` de Google Sheets (sigue redirecciones)."""
    import httpx

    response = httpx.get(export_url, follow_redirects=True, timeout=30.0)
    response.raise_for_status()
    return response.content


def _find_header_row(df: Any) -> int | None:
    keys = [_normalize(key) for key in KEY_COLUMNS]
    start = min(HEADER_SCAN_START, len(df))
    for index in range(start, len(df)):
        cells = [_normalize(value) for value in df.iloc[index].tolist()]
        matches = sum(1 for key in keys if any(key == cell or key in cell for cell in cells))
        if matches >= HEADER_MIN_MATCHES:
            return index
    return None


@router.get("/estadisticas")
async def get_hospitales_estadisticas() -> JSONResponse:
    """Devuelve el cuadro de estadísticas de la planilla de hospitales."""
    try:
        import pandas as pd
    except ImportError:  # pragma: no cover - dependencia declarada en requirements
        raise_http_error("INTERNAL", "pandas/openpyxl no están instalados en el backend.")

    if not SHEET_URL or not SHEET_URL.strip():
        raise_http_error("UNAVAILABLE", "La URL de Google Sheets no está configurada.")

    try:
        export_url = to_export_url(SHEET_URL)
    except ValueError as exc:
        raise_http_error("UNAVAILABLE", str(exc))

    try:
        content = _download_sheet(export_url)
        with pd.ExcelFile(io.BytesIO(content)) as excel:
            sheet_name = str(excel.sheet_names[0])
            raw = excel.parse(sheet_name=0, header=None)
    except Exception:  # noqa: BLE001 - se traduce a un error controlado
        raise_http_error("INTERNAL", "Error al conectar con Google Drive.")

    header_index = _find_header_row(raw)
    if header_index is None:
        raise_http_error(
            "UNPROCESSABLE",
            f"No se encontró el cuadro de estadísticas en la primera pestaña ('{sheet_name}').",
        )

    columns: list[str] = []
    for position, value in enumerate(raw.iloc[header_index].tolist()):
        name = "" if _is_empty(value) else _clean_name(value)
        columns.append(name or f"col_{position + 1}")

    data_rows: list[list[Any]] = []
    for row_index in range(header_index + 1, len(raw)):
        values = raw.iloc[row_index].tolist()
        if all(_is_empty(value) for value in values):
            break
        data_rows.append(values)

    # Excluye filas de totales (evita la doble suma de KPIs/gráfico).
    data_rows = [values for values in data_rows if not _is_total_row(values)]
    # Red de seguridad: si la última fila parece un gran total sin etiqueta.
    if data_rows and _looks_like_grand_total(data_rows):
        data_rows = data_rows[:-1]

    table = pd.DataFrame(data_rows, columns=columns)
    for column in columns[1:]:
        numeric = pd.to_numeric(table[column], errors="coerce").fillna(0)
        if len(numeric) and bool((numeric % 1 == 0).all()):
            numeric = numeric.astype("int64")
        table[column] = numeric
    if columns:
        first = columns[0]
        table[first] = table[first].apply(
            lambda value: "" if _is_empty(value) else str(value).strip()
        )

    records = json.loads(table.to_json(orient="records", force_ascii=False))

    # KPIs de las causas clave (sumando solo filas de datos; ausente → 0).
    by_name = {_normalize(column): column for column in columns}
    kpis: dict[str, int] = {}
    for key in KEY_COLUMNS:
        column = by_name.get(key)
        if column is None:
            column = next((c for c in columns[1:] if key in _normalize(c)), None)
        kpis[key.replace(" ", "_")] = int(table[column].sum()) if column else 0

    # Serie para el gráfico: una entrada por columna numérica (todas menos la 1ª),
    # sumando solo filas de datos, NaN/vacíos → 0, y filtrando las que queden en 0.
    chart_data = [
        {"causa": column, "cantidad": int(table[column].sum())}
        for column in columns[1:]
    ]
    chart_data = sorted(
        (item for item in chart_data if item["cantidad"] > 0),
        key=lambda item: (-item["cantidad"], item["causa"]),
    )

    return JSONResponse(
        status_code=200,
        content={
            "sheet": sheet_name,
            "columns": columns,
            "rows": records,
            "total_rows": len(records),
            "kpis": kpis,
            "chartData": chart_data,
        },
    )
