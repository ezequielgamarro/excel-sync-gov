"""Fila de la hoja «CONSULTAS» — validación y normalización (Pydantic v2).

Espeja las **20 columnas exactas** de la hoja oficial de la Jefatura y las
normaliza antes de persistirlas en ``app.consulta_event``. La validación es
*defensiva* (el origen no es frontera de confianza, §2.2.5): los textos se
recortan, ``turno`` se canoniza a mayúsculas y ``fecha_consulta`` acepta los
formatos ISO y es-CL (``DD/MM/YYYY``) usados en la planilla.

El modelo **no** rechaza la instantánea completa: una fila inválida se registra
como rechazo auditable y se descarta (misma política que las unidades/turnos
fuera de allowlist, RF-03.h).
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator

#: Orden exacto de las 20 columnas de la hoja «CONSULTAS».
CONSULTA_COLUMNS: tuple[str, ...] = (
    "fecha_consulta",
    "hora_consulta",
    "turno",
    "jerarquia",
    "personal_policial",
    "jefatura_regional",
    "dependencias",
    "tipo_consulta",
    "identificacion",
    "tipo_arma_vehiculo",
    "resultado",
    "causas_penales",
    "registro_legajo",
    "autoridad_judicial",
    "sistema_utilizado",
    "tramite_devuelto",
    "hora_resp",
    "personal_que_informa",
    "cargo",
    "operativos_preventivos",
)

_DMY_RE = re.compile(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$")


def _normalize_date(value: Any) -> Any:
    """Acepta ``date``/``datetime``/ISO y ``DD/MM/YYYY`` o ``DD-MM-YYYY``."""
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        text = value.strip()
        match = _DMY_RE.match(text)
        if match:
            day, month, year = (int(part) for part in match.groups())
            return date(year, month, day)
    return value


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


class ConsultaRow(BaseModel):
    """Una fila normalizada de la hoja «CONSULTAS».

    ``model_config`` descarta campos desconocidos (defensa ante columnas extra)
    y recorta espacios de todos los textos.
    """

    model_config = ConfigDict(extra="ignore", str_strip_whitespace=True)

    fecha_consulta: date
    hora_consulta: str = ""
    turno: str = ""
    jerarquia: str = ""
    personal_policial: str = ""
    jefatura_regional: str = ""
    dependencias: str = ""
    tipo_consulta: str = ""
    identificacion: str = ""
    tipo_arma_vehiculo: str = ""
    resultado: str = ""
    causas_penales: str = ""
    registro_legajo: str = ""
    autoridad_judicial: str = ""
    sistema_utilizado: str = ""
    tramite_devuelto: str = ""
    hora_resp: str = ""
    personal_que_informa: str = ""
    cargo: str = ""
    operativos_preventivos: str = ""

    @field_validator("fecha_consulta", mode="before")
    @classmethod
    def _coerce_fecha(cls, value: Any) -> Any:
        return _normalize_date(value)

    @field_validator("turno", mode="before")
    @classmethod
    def _normalize_turno(cls, value: Any) -> str:
        return _text(value).upper()

    @field_validator(
        "hora_consulta",
        "jerarquia",
        "personal_policial",
        "jefatura_regional",
        "dependencias",
        "tipo_consulta",
        "identificacion",
        "tipo_arma_vehiculo",
        "resultado",
        "causas_penales",
        "registro_legajo",
        "autoridad_judicial",
        "sistema_utilizado",
        "tramite_devuelto",
        "hora_resp",
        "personal_que_informa",
        "cargo",
        "operativos_preventivos",
        mode="before",
    )
    @classmethod
    def _coerce_text(cls, value: Any) -> str:
        return _text(value)
