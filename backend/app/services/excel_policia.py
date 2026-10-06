"""Extracción de métricas reales del workbook de la Policía (``EXCEL_POLICIA_URL``).

El endpoint público ``GET /api/estadisticas`` delega aquí. Este módulo:

- Normaliza enlaces de Google Sheets a su URL de descarga ``.xlsx``
  (``export?format=xlsx``), reutilizando la misma heurística que
  ``app.api.hospitales``.
- Descarga el workbook con ``httpx`` (sigue redirecciones) y lo abre con
  ``pandas.ExcelFile`` (``openpyxl``).
- Procesa **todas las hojas relevantes** detectadas por nombre (tolerando
  acentos/mayúsculas) o, en su defecto, por índice:
  ``DASHBOARD_WEB`` (regionales/dependencias/resultados), ``CONSULTAS``
  (incidentes por turno/tipo/regional/dependencia/resultado y logística de
  vehículos) y ``Data``/``ESTADISTICAS`` (comparativas semanales/mensuales).
- Limpia ``NaN``/vacíos → ``0`` y emite enteros en el formato ``{name, value}``
  que consumen los gráficos Recharts.

Los imports de ``pandas``/``httpx`` son **perezosos**. No se hardcodean
secretos ni se emite PII (solo etiquetas agregadas y conteos).
"""

from __future__ import annotations

import datetime as dt
import io
import math
import re
from typing import Any, Iterable, Mapping

#: Nombres candidatos de hoja (se comparan sin acentos ni mayúsculas).
DASHBOARD_SHEETS: tuple[str, ...] = ("DASHBOARD_WEB", "DASHBOARD WEB")
CONSULTAS_SHEETS: tuple[str, ...] = ("CONSULTAS",)
DATA_SHEETS: tuple[str, ...] = ("Data",)
ESTADISTICAS_SHEETS: tuple[str, ...] = ("ESTADISTICAS", "ESTADÍSTICAS")
POSITIVOS_SHEETS: tuple[str, ...] = ("Positivos", "POSITIVOS")

#: Orden oficial de los turnos operativos.
TURNO_ORDER: tuple[str, ...] = ("MAÑANA", "TARDE", "NOCHE")
#: Claves de tipo de consulta (logística / personas / armas).
TIPO_PERSONA = "PERSONA"
TIPO_VEHICULO = "VEHICULO"
TIPO_ARMA = "ARMA"

#: Ventana (en días) de cada valor del parámetro ``rango`` del endpoint público.
#: ``None``/desconocido → :data:`RANGO_DEFAULT` (default seguro).
RANGO_DIAS: dict[str, int] = {"ayer": 1, "semana": 7, "mes": 30, "anio": 365}
#: Default seguro cuando el parámetro falta o es inválido.
RANGO_DEFAULT = "anio"
#: Valores de ``rango`` que desactivan el filtro temporal (sin ventana).
RANGO_TODO: frozenset[str] = frozenset({"todo", "all"})

#: Traducción estricta sigla → nombre oficial de las Unidades Regionales.
#: Las claves están en mayúsculas (la comparación se normaliza sin acentos).
REGIONAL_MAP: dict[str, str] = {
    "URN": "Unidad Regional Norte",
    "URS": "Unidad Regional Sur",
    "URE": "Unidad Regional Este",
    "URO": "Unidad Regional Oeste",
    "URC": "Unidad Regional Capital",
}

#: Etiquetas geográficas basura que NO deben aparecer en las series (se comparan
#: con ``_normalize``: minúsculas, sin acentos y con espacios colapsados).
_EXCLUDED_GEO: frozenset[str] = frozenset({"iro", "cop", "regional, uuee"})

#: Mapeo estricto de siglas de dependencia (normalizadas) → nombre oficial.
_DEPENDENCIA_MAP: dict[str, str] = {
    "cria 9": "Comisaría Novena 9°",
}

#: Prefijo genérico ``CRIA `` → ``Comisaría `` (case-insensitive, solo al inicio).
_CRIA_RE = re.compile(r"^cria\b\s*", re.IGNORECASE)

#: Normalización de etiquetas de turno → turno operativo canónico.
_TURNO_LABELS: dict[str, str] = {
    "manana": "MAÑANA",
    "tarde": "TARDE",
    "noche": "NOCHE",
}

_ACCENT_MAP = str.maketrans("áéíóúüñÁÉÍÓÚÜÑ", "aeiouunAEIOUUN")
_SHEET_ID_RE = re.compile(r"/spreadsheets/d/([a-zA-Z0-9_-]+)")
_GID_RE = re.compile(r"[#?&]gid=(\d+)")
_TIME_RE = re.compile(r"(\d{1,2}):(\d{2})")
_EMPTY_TOKENS = ("", "nan", "none", "nat", "null", "#n/a", "-", "s/d")


# =============================================================================
# Utilidades de texto y valores
# =============================================================================
def _normalize(value: Any) -> str:
    """Normaliza a minúsculas sin acentos y con espacios colapsados."""
    text = str(value).translate(_ACCENT_MAP).strip().lower()
    return " ".join(text.split())


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return _normalize(value) in _EMPTY_TOKENS


def _clean_label(value: Any) -> str:
    """Colapsa saltos de línea/espacios múltiples y recorta."""
    return re.sub(r"\s+", " ", str(value)).strip()


def _is_excluded_geo(value: Any) -> bool:
    """True si la dependencia/regional es vacía o una etiqueta de descarte.

    Excluye nulos/``NaN`` y las siglas ``IRO``, ``COP`` y ``REGIONAL, UUEE``
    (comparadas sin acentos ni mayúsculas) para que nunca lleguen al JSON.
    """
    if _is_empty(value):
        return True
    return _normalize(value) in _EXCLUDED_GEO


def _translate_regional(value: Any) -> str:
    """Traduce una sigla regional (``URN``/``URS``/``URE``/``URO``/``URC``).

    Tolerante a mayúsculas/minúsculas, acentos y espacios. Si la forma
    normalizada no coincide con ``REGIONAL_MAP`` se devuelve el valor limpio
    original (p. ej. ``"IRO"`` permanece ``"IRO"``).
    """
    if _is_empty(value):
        return ""
    label = _clean_label(value)
    key = _normalize(label).upper()
    return REGIONAL_MAP.get(key, label)


def _clean_dependencia(value: Any) -> str:
    """Normaliza el nombre de una dependencia policial.

    - Vacío/``NaN`` → ``""``.
    - Mapeo estricto primero: ``CRIA 9`` → ``Comisaría Novena 9°``.
    - Prefijo genérico: ``CRIA `` → ``Comisaría `` (``CRIA 13`` → ``Comisaría 13``,
      ``CRIA YERBA BUENA`` → ``Comisaría YERBA BUENA``).
    - El resto de etiquetas se conserva (colapsando espacios).
    """
    if _is_empty(value):
        return ""
    label = _clean_label(value)
    mapped = _DEPENDENCIA_MAP.get(_normalize(label))
    if mapped is not None:
        return mapped
    return _clean_label(_CRIA_RE.sub("Comisaría ", label))


def _translate_series(
    items: Iterable[Mapping[str, Any]], translate: Any = None
) -> list[dict[str, Any]]:
    """Aplica ``translate`` a los nombres de una serie y suma duplicados.

    Conserva el orden de primera aparición; las siglas que mapean al mismo
    nombre oficial (p. ej. ``URC`` y "Unidad Regional Capital") se agregan.
    """
    translator = translate or _translate_regional
    order: list[str] = []
    counter: dict[str, int] = {}
    for item in items:
        name = _clean_label(translator(item.get("name", "")))
        if not name:
            continue
        if name not in counter:
            order.append(name)
        counter[name] = counter.get(name, 0) + int(item.get("value", 0) or 0)
    return [{"name": name, "value": counter[name]} for name in order]


def _geo_series(items: Iterable[Mapping[str, Any]], clean: Any = None) -> list[dict[str, Any]]:
    """Aplica ``clean`` a una serie geográfica, excluye basura y suma duplicados.

    Descarta ``IRO``/``COP``/``REGIONAL, UUEE``/nulos y limpia el nombre con
    ``clean`` (``_clean_dependencia`` o ``_translate_regional``). Conserva el
    orden de primera aparición.
    """
    cleaner = clean or _clean_dependencia
    order: list[str] = []
    counter: dict[str, int] = {}
    for item in items:
        raw = item.get("name", "")
        if _is_excluded_geo(raw):
            continue
        name = _clean_label(cleaner(raw))
        if not name:
            continue
        if name not in counter:
            order.append(name)
        counter[name] = counter.get(name, 0) + int(item.get("value", 0) or 0)
    return [{"name": name, "value": counter[name]} for name in order]


def _count_geo(values: Iterable[Any], clean: Any = None) -> dict[str, int]:
    """Cuenta valores geográficos limpiando el nombre y excluyendo la basura."""
    cleaner = clean or _clean_dependencia
    counter: dict[str, int] = {}
    for value in values:
        if _is_excluded_geo(value):
            continue
        name = _clean_label(cleaner(value))
        if not name:
            continue
        counter[name] = counter.get(name, 0) + 1
    return counter


def _to_int(value: Any) -> int:
    """Convierte una celda a entero; no numérica/NaN → 0."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return 0
    try:
        return int(float(str(value).strip().replace(",", "")))
    except (TypeError, ValueError):
        return 0


def _series_from_counts(
    counter: Mapping[str, int], order: Iterable[str] | None = None
) -> list[dict[str, Any]]:
    """Convierte un contador en ``[{"name", "value"}]`` con orden determinista."""
    items = [
        {"name": name, "value": int(value)}
        for name, value in counter.items()
        if name and not _is_empty(name)
    ]
    if order is not None:
        rank = {name: index for index, name in enumerate(order)}
        items.sort(key=lambda item: (rank.get(item["name"], len(rank)), item["name"]))
    else:
        items.sort(key=lambda item: (-item["value"], item["name"]))
    return items


def _rango_dias(rango: str | None) -> int | None:
    """Días de la ventana ACTUAL para ``rango``; ``None`` si no se filtra.

    Valores aceptados: ``ayer`` (1), ``semana`` (7), ``mes`` (30), ``anio``
    (365). ``todo``/``all`` desactivan el filtro. Cualquier otro valor
    (incluido ``None``) cae al default seguro ``anio``.
    """
    key = _normalize(rango) if rango else ""
    if key in RANGO_TODO:
        return None
    if key in RANGO_DIAS:
        return RANGO_DIAS[key]
    return RANGO_DIAS[RANGO_DEFAULT]


def _ranking_top5(
    actual: Mapping[str, int], anterior: Mapping[str, int] | None = None
) -> list[dict[str, Any]]:
    """Top 5 de dependencias por intervenciones, con variación real.

    Ordena por conteo de la ventana ACTUAL (desc, desempate alfabético), corta
    a 5 e incluye ``intervenciones``/``value`` (actual), ``variacion_abs`` y
    ``variacion_pct`` (``None`` si el período anterior no tiene base > 0; NUNCA
    se inventa ``0``).
    """
    prev = anterior or {}
    ranked = sorted(actual.items(), key=lambda kv: (-int(kv[1]), kv[0]))[:5]
    items: list[dict[str, Any]] = []
    for name, count in ranked:
        current = int(count)
        previous = int(prev.get(name, 0))
        variacion_abs = current - previous
        variacion_pct = round(variacion_abs / previous * 100, 2) if previous > 0 else None
        items.append(
            {
                "name": name,
                "intervenciones": current,
                "value": current,
                "variacion_abs": variacion_abs,
                "variacion_pct": variacion_pct,
            }
        )
    return items


def _count_values(values: Iterable[Any]) -> dict[str, int]:
    counter: dict[str, int] = {}
    for value in values:
        if _is_empty(value):
            continue
        name = _clean_label(value)
        if not name:
            continue
        counter[name] = counter.get(name, 0) + 1
    return counter


def _hour_of(value: Any) -> int | None:
    """Hora (0-23) de una celda ``time``/``datetime``/texto; ``None`` si no hay."""
    if isinstance(value, dt.datetime):
        return value.hour
    if isinstance(value, dt.time):
        return value.hour
    if _is_empty(value):
        return None
    match = _TIME_RE.search(str(value))
    if not match:
        return None
    hour = int(match.group(1))
    return hour if 0 <= hour <= 23 else None


def _turno_of(value: Any) -> str | None:
    """Mapea la hora al turno operativo (MAÑANA 06-14, TARDE 14-22, NOCHE resto)."""
    hour = _hour_of(value)
    if hour is None:
        return None
    if 6 <= hour < 14:
        return "MAÑANA"
    if 14 <= hour < 22:
        return "TARDE"
    return "NOCHE"


def _turno_label(value: Any) -> str | None:
    """Normaliza una etiqueta de turno a ``MAÑANA``/``TARDE``/``NOCHE``.

    Tolera acentos/mayúsculas y textos como ``"Turno Mañana"``. Si el valor no
    es una etiqueta reconocida se intenta derivar de la hora; en cualquier otro
    caso devuelve ``None`` (turno vacío/desconocido).
    """
    if _is_empty(value):
        return None
    key = _normalize(value)
    direct = _TURNO_LABELS.get(key)
    if direct is not None:
        return direct
    for token, label in _TURNO_LABELS.items():
        if token in key:
            return label
    return _turno_of(value)


#: Formatos de fecha aceptados por :func:`_date_of` (además de ``datetime``/``date``).
_DATE_FORMATS: tuple[str, ...] = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d")


def _date_of(value: Any) -> dt.date | None:
    """Convierte una celda fecha/``datetime``/texto en ``date``; si no, ``None``.

    Soporta ``datetime``/``date``, ISO ``YYYY-MM-DD`` (con o sin hora),
    ``DD/MM/YYYY``, ``DD-MM-YYYY`` y ``YYYY/MM/DD``.
    """
    if _is_empty(value):
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    text = _clean_label(value)
    candidate = text.split(" ", 1)[0] if " " in text else text
    for fmt in _DATE_FORMATS:
        try:
            return dt.datetime.strptime(candidate, fmt).date()
        except ValueError:
            continue
    try:
        return dt.datetime.fromisoformat(text).date()
    except ValueError:
        return None


def _month_of(value: Any) -> str | None:
    """Mes ``YYYY-MM`` de una celda fecha; ``None`` si no se puede parsear."""
    date = _date_of(value)
    return date.strftime("%Y-%m") if date is not None else None


def _daymonth_of(value: Any) -> str | None:
    """Día ``DD/MM`` de una celda fecha; ``None`` si no se puede parsear."""
    date = _date_of(value)
    return date.strftime("%d/%m") if date is not None else None


def _day_of(value: Any) -> str | None:
    """Día ISO (``YYYY-MM-DD``) de una celda fecha/``datetime``/texto; si no, ``None``."""
    date = _date_of(value)
    return date.isoformat() if date is not None else None


# =============================================================================
# Google Sheets / descarga
# =============================================================================
def to_export_url(url: str) -> str:
    """Convierte un enlace de Google Sheets en URL de descarga directa ``.xlsx``.

    Acepta ``.../edit?usp=sharing`` y ``.../edit#gid=123`` (preserva el ``gid``).
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


def _find_sheet(sheet_names: list[str], candidates: tuple[str, ...]) -> str | None:
    """Localiza una hoja por nombre tolerando acentos/mayúsculas."""
    norm = {_normalize(name): name for name in sheet_names}
    for candidate in candidates:
        found = norm.get(_normalize(candidate))
        if found is not None:
            return found
    return None


# =============================================================================
# Extracción de series
# =============================================================================
def _extract_series(
    frame: Any, name_index: int, value_index: int, drop_label: str
) -> list[dict[str, Any]]:
    """Extrae ``[{"name": str, "value": int}]`` de dos columnas posicionales.

    Descarta filas sin nombre o sin valor numérico (``NaN``) y la fila de
    encabezado cuyo nombre coincide con ``drop_label``.
    """
    import pandas as pd

    subset = frame.iloc[:, [name_index, value_index]].copy()
    subset.columns = ["name", "value"]
    subset["name"] = subset["name"].astype("string").str.strip()
    subset["value"] = pd.to_numeric(subset["value"], errors="coerce")
    subset = subset.dropna(subset=["name", "value"])
    subset = subset[(subset["name"] != drop_label) & (subset["name"] != "")]
    if subset.empty:
        return []
    subset["value"] = subset["value"].astype("int64")
    return [
        {"name": str(record["name"]), "value": int(record["value"])}
        for record in subset[["name", "value"]].to_dict(orient="records")
    ]


def _dashboard_series(frame: Any) -> dict[str, list[dict[str, Any]]]:
    """Series de ``DASHBOARD_WEB`` (mismo formato que el contrato original)."""
    return {
        "grafico_regionales": _geo_series(
            _extract_series(frame, 0, 1, "REGIONAL"), _translate_regional
        ),
        "grafico_dependencias": _geo_series(
            _extract_series(frame, 3, 4, "DEPENDENCIA"), _clean_dependencia
        ),
        "alertas_resultados": _extract_series(frame, 6, 7, "RESULTADO"),
    }


def _consulta_columns(frame: Any) -> tuple[int, dict[str, int]] | None:
    """Detecta la fila de encabezado y los índices de columna de ``CONSULTAS``.

    Devuelve ``(header_index, {campo: columna})`` o ``None`` si no se reconoce.
    """
    for index in range(min(len(frame), 10)):
        cells = [_normalize(value) for value in frame.iloc[index].tolist()]
        mapping: dict[str, int] = {}
        for position, cell in enumerate(cells):
            if not cell:
                continue
            if cell == "dia":
                mapping.setdefault("dia", position)
                mapping.setdefault("fecha", position)
            elif cell == "fecha" or cell.startswith("fecha"):
                mapping.setdefault("fecha", position)
            elif cell == "hora":
                mapping.setdefault("hora", position)
            elif cell.startswith("turno"):
                mapping.setdefault("turno", position)
            elif cell.startswith("jerarquia"):
                mapping.setdefault("jerarquia", position)
            elif cell in ("dependencia", "dependencias"):
                mapping.setdefault("dependencia", position)
            elif cell.startswith("regional"):
                mapping.setdefault("regional", position)
            elif cell.startswith("consulta"):
                mapping.setdefault("consulta", position)
            elif cell.startswith("resultado"):
                mapping.setdefault("resultado", position)
        # Red de seguridad: columnas con nombres más largos (p. ej. "… DEPENDENCIAS").
        if "dependencia" not in mapping:
            for position, cell in enumerate(cells):
                if "dependencia" in cell and "personal" not in cell:
                    mapping["dependencia"] = position
                    break
        if ("hora" in mapping or "turno" in mapping) and (
            "consulta" in mapping or "resultado" in mapping
        ):
            return index, mapping
    return None


def _consultas_series(frame: Any, rango: str | None = None) -> dict[str, Any]:
    """Series agregadas derivadas de la hoja ``CONSULTAS``.

    ``rango`` (``ayer``/``semana``/``mes``/``anio``; ``todo`` sin filtro)
    recorta las filas a la ventana móvil que termina en la fecha máxima real
    ANTES de agregar cualquier métrica.
    """
    detected = _consulta_columns(frame)
    if detected is None:
        return {}
    header_index, columns = detected
    rows = frame.iloc[header_index + 1 :]

    import pandas as pd  # import perezoso (solo si hay hoja CONSULTAS)

    # Columna de fecha: se prefiere "fecha" (fecha/fecha consulta) y se cae a "dia".
    date_key = "fecha" if "fecha" in columns else ("dia" if "dia" in columns else None)
    fechas = rows.iloc[:, columns[date_key]] if date_key is not None else None
    horas = rows.iloc[:, columns["hora"]] if "hora" in columns else None
    # Fila válida: al menos una referencia temporal (fecha u hora). Si la hoja
    # dedicara sólo una columna `TURNO` (sin fecha/hora), no se descarta ninguna.
    if horas is not None and fechas is not None:
        valid = ~(horas.apply(_is_empty) & fechas.apply(_is_empty))
    elif horas is not None:
        valid = ~horas.apply(_is_empty)
    elif fechas is not None:
        valid = ~fechas.apply(_is_empty)
    else:
        valid = pd.Series(True, index=rows.index)

    valid_rows = rows.loc[valid, :]

    # --- Filtro temporal global (ANTES de agregar cualquier métrica) -------
    # Ventana ACTUAL = [anchor-(d-1), anchor]; ANTERIOR (misma longitud) =
    # [anchor-(2d-1), anchor-d]. El ancla es la fecha máxima real (o hoy).
    dias = _rango_dias(rango)
    previous_rows = valid_rows.iloc[0:0]
    if date_key is not None and dias is not None:
        parsed = [_date_of(value) for value in valid_rows.iloc[:, columns[date_key]]]
        parsed_dates = [value for value in parsed if value is not None]
        anchor = max(parsed_dates) if parsed_dates else dt.date.today()
        current_start = anchor - dt.timedelta(days=dias - 1)
        previous_start = anchor - dt.timedelta(days=2 * dias - 1)
        previous_end = anchor - dt.timedelta(days=dias)
        current_mask = pd.Series(
            [value is not None and current_start <= value <= anchor for value in parsed],
            index=valid_rows.index,
        )
        previous_mask = pd.Series(
            [value is not None and previous_start <= value <= previous_end for value in parsed],
            index=valid_rows.index,
        )
        previous_rows = valid_rows.loc[previous_mask, :]
        valid_rows = valid_rows.loc[current_mask, :]

    def col(name: str, subset: Any = None) -> Any:
        source = valid_rows if subset is None else subset
        if name not in columns:
            return []
        return source.iloc[:, columns[name]]

    tipo_values = list(col("consulta"))
    resultado_values = list(col("resultado"))
    fecha_values = list(col(date_key)) if date_key is not None else []
    tipo_norm = [_normalize(value) for value in tipo_values]
    resultado_norm = [_normalize(value) for value in resultado_values]

    # Turno: si existe columna dedicada se usa su etiqueta; si no, se deriva de
    # la hora. En ambos casos se descartan las filas sin turno válido
    # (vacío/NaN/blanco o no reconocido) para que no aparezcan categorías vacías.
    if "turno" in columns:
        turno_labels = [_turno_label(value) for value in col("turno")]
    else:
        turno_labels = [_turno_of(value) for value in col("hora")]

    by_tipo = _count_values(tipo_values)
    by_resultado = _count_values(resultado_values)
    # Regionales/dependencias: se excluye IRO/COP/REGIONAL, UUEE/nulos y se
    # limpian las siglas (``CRIA`` → ``Comisaría``).
    by_regional = _count_geo(col("regional"), _translate_regional)
    by_dependencia = _count_geo(col("dependencia"), _clean_dependencia)
    by_dependencia_prev = _count_geo(col("dependencia", previous_rows), _clean_dependencia)
    by_jerarquia = _count_values(col("jerarquia"))
    by_dia = (
        _count_values(day for day in (col(date_key).apply(_day_of)) if day)
        if date_key is not None
        else {}
    )
    by_hora = (
        {
            f"{int(hour):02d}:00": count
            for hour, count in _count_values(
                hour for hour in (col("hora").apply(_hour_of)) if hour is not None
            ).items()
        }
        if "hora" in columns
        else {}
    )

    persona_norm = _normalize(TIPO_PERSONA)
    tipo_vehiculo = _normalize(TIPO_VEHICULO)
    tipo_arma = _normalize(TIPO_ARMA)

    # Meses y KPIs reales. El workbook real NO trae columna dedicada de
    # aprehendidos/detenidos; su origen exacto es la hoja ``Positivos`` (total
    # global, sin desglose mensual). Por eso el desglose por mes deriva
    # ``aprehendidos`` como PERSONA con resultado POSITIVO (única señal por fila);
    # ``parse_workbook`` sobreescribe el total global con la hoja ``Positivos``.
    por_mes: dict[str, dict[str, int]] = {}
    mes_order: list[str] = []
    aprehendidos = 0
    for position, raw_fecha in enumerate(fecha_values):
        mes = _month_of(raw_fecha)
        if mes is None:
            continue
        tipo = tipo_norm[position] if position < len(tipo_norm) else ""
        resultado = resultado_norm[position] if position < len(resultado_norm) else ""
        if mes not in por_mes:
            por_mes[mes] = {
                "total_consultas": 0,
                "aprehendidos": 0,
                "vehiculos": 0,
                "armas": 0,
            }
            mes_order.append(mes)
        entry = por_mes[mes]
        entry["total_consultas"] += 1
        if tipo == persona_norm and "positiv" in resultado:
            entry["aprehendidos"] += 1
            aprehendidos += 1
        if tipo == tipo_vehiculo:
            entry["vehiculos"] += 1
        if tipo == tipo_arma:
            entry["armas"] += 1

    meses_ordenados = sorted(mes_order)
    por_mes_series = [{"mes": mes, **por_mes[mes]} for mes in meses_ordenados]
    consultas_por_mes = [
        {"name": mes, "value": por_mes[mes]["total_consultas"]} for mes in meses_ordenados
    ]

    # Ranking Top 5 por dependencia (ya limpia/filtrada), descendente, con la
    # variación real actual vs la ventana inmediatamente anterior.
    dependencias_series = _series_from_counts(by_dependencia)
    ranking_top5 = _ranking_top5(by_dependencia, by_dependencia_prev)

    # Incidentes de turnos por día (evolución diaria para gráficos).
    turno_por_dia: dict[str, dict[str, int]] = {}
    turno_por_dia_fechas: dict[str, dt.date] = {}
    turno_key = {"MAÑANA": "mañana", "TARDE": "tarde", "NOCHE": "noche"}
    for raw_fecha, turno in zip(fecha_values, turno_labels, strict=False):
        if not turno:
            continue
        fecha = _date_of(raw_fecha)
        if fecha is None:
            continue
        dia = fecha.strftime("%d/%m")
        if dia not in turno_por_dia:
            turno_por_dia[dia] = {"mañana": 0, "tarde": 0, "noche": 0}
            turno_por_dia_fechas[dia] = fecha
        key = turno_key.get(turno)
        if key is not None:
            turno_por_dia[dia][key] += 1
    incidentes_turno_por_dia = [
        {"fecha": dia, **turno_por_dia[dia]}
        for dia in sorted(turno_por_dia, key=lambda item: turno_por_dia_fechas[item])
    ]

    # Evolución diaria ESTRICTA: un punto por día con incidentes (columna Fecha),
    # sin agrupar globalmente por turno. Excluye días nulos/sin fecha y sale en
    # orden cronológico como ``[{"fecha": "DD/MM", "total": int}]``.
    fecha_por_dia: dict[str, int] = {}
    fecha_por_dia_orden: dict[str, dt.date] = {}
    for raw_fecha in fecha_values:
        fecha = _date_of(raw_fecha)
        if fecha is None:
            continue
        dia = fecha.strftime("%d/%m")
        fecha_por_dia_orden[dia] = fecha
        fecha_por_dia[dia] = fecha_por_dia.get(dia, 0) + 1
    incidentes_por_fecha = [
        {"fecha": dia, "total": fecha_por_dia[dia]}
        for dia in sorted(fecha_por_dia, key=lambda item: fecha_por_dia_orden[item])
    ]

    # Logística: se aísla el subconjunto de consultas de VEHICULO/ARMA.
    def filtered(subset_norm: str, field: str) -> list[dict[str, Any]]:
        mask = [value == subset_norm for value in tipo_norm]
        if not any(mask) or field not in columns:
            return []
        series = valid_rows.iloc[:, columns[field]]
        values = [value for value, keep in zip(series, mask, strict=False) if keep]
        if field == "regional":
            return _series_from_counts(_count_geo(values, _translate_regional))
        if field == "dependencia":
            return _series_from_counts(_count_geo(values, _clean_dependencia))
        return _series_from_counts(_count_values(values))

    return {
        "incidentes_por_fecha": incidentes_por_fecha,
        "incidentes_por_dia": _series_from_counts(by_dia, order=sorted(by_dia)),
        "incidentes_por_hora": _series_from_counts(by_hora, order=sorted(by_hora)),
        "incidentes_por_tipo": _series_from_counts(by_tipo),
        "incidentes_por_regional": _series_from_counts(by_regional),
        "incidentes_por_dependencia": dependencias_series,
        "incidentes_por_resultado": _series_from_counts(by_resultado),
        "incidentes_por_jerarquia": _series_from_counts(by_jerarquia),
        "distribucion_incidentes": _series_from_counts(by_tipo),
        "logistica_vehiculos_por_regional": filtered(tipo_vehiculo, "regional"),
        "logistica_vehiculos_por_dependencia": filtered(tipo_vehiculo, "dependencia"),
        "logistica_armas_por_regional": filtered(tipo_arma, "regional"),
        "logistica_armas_por_dependencia": filtered(tipo_arma, "dependencia"),
        "por_mes": por_mes_series,
        "consultas_por_mes": consultas_por_mes,
        "rankingTop5": ranking_top5,
        "regionales_disponibles": sorted(by_regional),
        "dependencias_disponibles": sorted(by_dependencia),
        "incidentes_turno_por_dia": incidentes_turno_por_dia,
        "kpis": {
            "total_consultas": len(valid_rows),
            "aprehendidos": aprehendidos,
            "personas": int(by_tipo.get(TIPO_PERSONA, 0)),
            "vehiculos": int(by_tipo.get(TIPO_VEHICULO, 0)),
            "armas": int(by_tipo.get(TIPO_ARMA, 0)),
            "positivos": int(by_resultado.get("POSITIVO", 0)),
            "negativos": int(by_resultado.get("NEGATIVO", 0)),
        },
        "totales": {
            "total_consultas": len(valid_rows),
            "aprehendidos": aprehendidos,
            "vehiculos_secuestrados": int(by_tipo.get(TIPO_VEHICULO, 0)),
            "armas_secuestradas": int(by_tipo.get(TIPO_ARMA, 0)),
        },
    }


def _comparativas_series(frame: Any) -> dict[str, Any]:
    """Comparativas semanales/mensuales derivadas de ``Data``/``ESTADISTICAS``."""
    header_index: int | None = None
    for index in range(min(len(frame), 10)):
        cells = [_normalize(value) for value in frame.iloc[index].tolist()]
        if "semana" in cells and any("mes" in cell for cell in cells):
            header_index = index
            break
    if header_index is None:
        return {"comparativas_semanales": [], "comparativas_mensuales": [], "comparativas": []}

    header = [_normalize(value) for value in frame.iloc[header_index].tolist()]
    try:
        mes_col = header.index("mes")
        semana_col = header.index("semana")
    except ValueError:
        return {"comparativas_semanales": [], "comparativas_mensuales": [], "comparativas": []}
    cantidad_col = next((i for i, cell in enumerate(header) if "cantidad" in cell), None)

    rows = frame.iloc[header_index + 1 :]
    semanales: list[dict[str, Any]] = []
    mensuales: dict[str, int] = {}
    for _, row in rows.iterrows():
        values = row.tolist()
        if mes_col >= len(values):
            continue
        mes = _clean_label(values[mes_col])
        if _is_empty(mes) or _normalize(mes) == "total":
            continue
        semana = (
            _clean_label(values[semana_col])
            if semana_col < len(values) and not _is_empty(values[semana_col])
            else ""
        )
        cantidad = (
            _to_int(values[cantidad_col])
            if cantidad_col is not None and cantidad_col < len(values)
            else 0
        )
        name = f"{mes} {semana}".strip()
        semanales.append({"name": name, "value": cantidad})
        mensuales[mes] = mensuales.get(mes, 0) + cantidad

    mensual_series = _series_from_counts(mensuales)
    return {
        "comparativas_semanales": semanales,
        "comparativas_mensuales": mensual_series,
        "comparativas": mensual_series,
    }


def _estadisticas_totales(frame: Any) -> dict[str, int]:
    """Totales («Total del Mes» / «Total General») de la hoja ``ESTADISTICAS``."""
    totales: dict[str, int] = {}
    for _, row in frame.iterrows():
        values = row.tolist()
        for position, cell in enumerate(values):
            label = _normalize(cell).rstrip(":")
            if label in ("total del mes", "total general") and position + 1 < len(values):
                key = "total_mes" if "mes" in label else "total_general"
                totales.setdefault(key, _to_int(values[position + 1]))
    return totales


def _aprehendidos_from_positivos_sheet(excel: Any, sheet_names: list[str]) -> int | None:
    """Lee el total global de la hoja ``Positivos`` (origen exacto de aprehendidos).

    El workbook real no expone una columna dedicada de aprehendidos/detenidos,
    pero sí una hoja ``Positivos`` con un total global (p. ej. ``POSITIVOS 25``).
    Devuelve ``None`` si la hoja no existe o no tiene un valor legible.
    """
    name = _find_sheet(sheet_names, POSITIVOS_SHEETS)
    if name is None:
        return None
    try:
        frame = excel.parse(sheet_name=name, header=None)
    except Exception:  # noqa: BLE001
        return None
    for _, row in frame.iterrows():
        values = row.tolist()
        for position, cell in enumerate(values):
            label = _normalize(cell)
            if label in ("positivos", "aprehendidos", "aprehendido", "detenidos", "detenido"):
                for follow in values[position + 1 :]:
                    if not _is_empty(follow) and _to_int(follow) > 0:
                        return _to_int(follow)
    return None


# =============================================================================
# Punto de entrada
# =============================================================================
def parse_workbook(content: bytes, rango: str | None = None) -> dict[str, Any]:
    """Procesa el ``.xlsx`` ya descargado y devuelve las métricas agregadas.

    ``rango`` recorta la hoja ``CONSULTAS`` a la ventana temporal elegida
    (``ayer``/``semana``/``mes``/``anio``; ``todo`` sin filtro) ANTES de agregar.
    """
    import pandas as pd

    with pd.ExcelFile(io.BytesIO(content)) as excel:
        sheet_names = [str(name) for name in excel.sheet_names]
        dashboard_name = _find_sheet(sheet_names, DASHBOARD_SHEETS)
        consultas_name = _find_sheet(sheet_names, CONSULTAS_SHEETS)
        data_name = _find_sheet(sheet_names, DATA_SHEETS) or _find_sheet(
            sheet_names, ESTADISTICAS_SHEETS
        )

        result: dict[str, Any] = {
            "grafico_regionales": [],
            "grafico_dependencias": [],
            "alertas_resultados": [],
            "intervenciones_por_unidad": [],
            "consultas_por_dependencia": [],
            "incidentes_por_fecha": [],
            "incidentes_por_dia": [],
            "incidentes_por_hora": [],
            "incidentes_por_tipo": [],
            "incidentes_por_regional": [],
            "incidentes_por_dependencia": [],
            "incidentes_por_resultado": [],
            "incidentes_por_jerarquia": [],
            "distribucion_incidentes": [],
            "logistica_vehiculos_por_regional": [],
            "logistica_vehiculos_por_dependencia": [],
            "logistica_armas_por_regional": [],
            "logistica_armas_por_dependencia": [],
            "vehiculosPorRegional": [],
            "armasPorRegional": [],
            "por_mes": [],
            "consultas_por_mes": [],
            "rankingTop5": [],
            "regionales_disponibles": [],
            "dependencias_disponibles": [],
            "incidentes_turno_por_dia": [],
            "comparativas": [],
            "comparativas_semanales": [],
            "comparativas_mensuales": [],
            "kpis": {
                "total_consultas": 0,
                "aprehendidos": 0,
                "personas": 0,
                "vehiculos": 0,
                "armas": 0,
                "positivos": 0,
                "negativos": 0,
            },
            "totales": {
                "total_consultas": 0,
                "aprehendidos": 0,
                "vehiculos_secuestrados": 0,
                "armas_secuestradas": 0,
            },
            "estadisticas_totales": {},
            "hojas": sheet_names,
        }

        if dashboard_name is not None:
            try:
                frame = excel.parse(sheet_name=dashboard_name, header=None)
                result.update(_dashboard_series(frame))
            except Exception:  # noqa: BLE001 - una hoja mala no invalida el resto
                pass

        if consultas_name is not None:
            try:
                frame = excel.parse(sheet_name=consultas_name, header=None)
                result.update(_consultas_series(frame, rango=rango) or {})
            except Exception:  # noqa: BLE001
                pass

        if data_name is not None:
            try:
                frame = excel.parse(sheet_name=data_name, header=None)
                result.update(_comparativas_series(frame))
            except Exception:  # noqa: BLE001
                pass

        estadisticas_name = _find_sheet(sheet_names, ESTADISTICAS_SHEETS)
        if estadisticas_name is not None:
            try:
                frame = excel.parse(sheet_name=estadisticas_name, header=None)
                result["estadisticas_totales"] = _estadisticas_totales(frame)
            except Exception:  # noqa: BLE001
                pass

        # Origen exacto del total de aprehendidos: hoja ``Positivos`` (global).
        # El desglose ``por_mes[].aprehendidos`` sigue siendo la derivación por
        # fila (PERSONA + POSITIVO), única señal desagregable por mes.
        aprehendidos_sheet = _aprehendidos_from_positivos_sheet(excel, sheet_names)
        if aprehendidos_sheet is not None:
            result["kpis"]["aprehendidos"] = aprehendidos_sheet
            result["totales"]["aprehendidos"] = aprehendidos_sheet

    # «Intervenciones por Unidad» = CONTEO REAL por rango de la hoja CONSULTAS
    # (``incidentes_por_regional``), sin multiplicadores ni snapshot pre-agregado
    # de DASHBOARD_WEB. «Consultas por Dependencia» conserva el alias histórico.
    result["intervenciones_por_unidad"] = list(result.get("incidentes_por_regional", []))
    result["consultas_por_dependencia"] = list(result.get("grafico_dependencias", []))
    # Aliases camelCase de logística por Unidad Regional (contrato del frontend).
    result["vehiculosPorRegional"] = list(result.get("logistica_vehiculos_por_regional", []))
    result["armasPorRegional"] = list(result.get("logistica_armas_por_regional", []))

    return result


def build_estadisticas(url: str, rango: str | None = None) -> dict[str, Any]:
    """Descarga el workbook de ``url`` y devuelve las métricas agregadas.

    ``rango`` se propaga a :func:`parse_workbook` (ventana temporal de
    ``CONSULTAS``). Lanza la excepción subyacente ante fallo total de
    red/lectura (el endpoint lo traduce a ``{"estado": "error", ...}``).
    """
    export_url = to_export_url(url)
    content = _download_sheet(export_url)
    return parse_workbook(content, rango=rango)
