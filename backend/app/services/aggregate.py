"""Cálculo de agregados y variación "vs ayer" (spec §7.3/§7.3.1, §7.4, T33).

El backend es la **única fuente de verdad** de la variación respecto a ayer
(§7.1): aunque el agente envíe ``baseline_value``/``variacion_*`` como *hint*,
aquí se recalculan de forma autoritativa a partir de los agregados de PostgreSQL
(``agg_hourly``/``agg_daily``), de modo que todos los operadores ven exactamente
la misma cifra (sin divergencia por zona horaria del cliente, RNF-15).

Bases de comparación (OD-02):

- **KPIs** → ``ayer_mismo_tramo``: acumulado del día anterior hasta la misma
  hora. Como ``agg_hourly`` guarda el **valor absoluto acumulado** por hora, el
  baseline es el valor del último bucket de ayer con hora ≤ hora actual.
- **Turnos** → ``ayer_mismo_turno``: el mismo turno operativo del día anterior
  (``agg_daily``).

Reglas de negocio (§7.3):

- ``delta_abs = value − baseline_value``; ``delta_pct = round(delta_abs /
  baseline_value × 100, 2)``.
- ``baseline_value == 0`` → ``delta_pct = null``, ``has_reference = true``,
  ``delta_abs = value``.
- Sin registro de ayer → ``has_reference = false``, ``delta_abs = null``,
  ``delta_pct = null``.
- ``direction`` deriva de ``delta_abs`` (up/down/flat), nunca del porcentaje.

Los baselines se cachean por ``data_date`` (+ ``turno_id``/hora) para no
recalcular por petición (RISK-05). El formato numérico es-CL (miles con punto,
decimal con coma) se expone como helpers de **presentación**; los valores en el
wire son **crudos** (enteros/flotantes) para cálculo (RNF-15.b).
"""

from __future__ import annotations

import copy
import time as _time
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.tables import KPIS, TURNOS, agg_daily, agg_hourly

# Zona horaria canónica (cacheada por proceso; §13, OD-01).
_canonical_tz: ZoneInfo | None = None


def canonical_tz() -> ZoneInfo:
    """Devuelve la zona horaria canónica (IANA) cacheada por proceso."""
    global _canonical_tz
    if _canonical_tz is None:
        _canonical_tz = ZoneInfo(get_settings().canonical_timezone)
    return _canonical_tz


# =============================================================================
# Formato numérico es-CL (presentación; RNF-15.b)
# =============================================================================


def format_int_es_cl(value: int) -> str:
    """Formatea un entero con separador de miles (punto): ``184732`` → ``184.732``."""
    return f"{value:,}".replace(",", ".")


def format_decimal_es_cl(value: float | int, *, decimals: int = 2) -> str:
    """Formatea un decimal con coma decimal: ``1.71`` → ``1,71``."""
    return f"{value:.{decimals}f}".replace(".", ",")


def format_pct_es_cl(value: float | int | None, *, decimals: int = 1) -> str:
    """Formatea un porcentaje con coma decimal (``1.7`` → ``1,7``); ``None`` → ``—``."""
    if value is None:
        return "—"
    return f"{value:.{decimals}f}".replace(".", ",")


# =============================================================================
# Caché de baselines (por data_date + turno_id / hora; RISK-05)
# =============================================================================


class BaselineCache:
    """Caché en memoria con TTL para baselines (evita recalcular por petición).

    No es distribuida (igual que el resto de fallbacks de F4): con varias
    réplicas cada una cachea por separado, pero el valor es determinista (deriva
    de PostgreSQL), por lo que no hay divergencia.
    """

    def __init__(self, ttl_seconds: float = 60.0) -> None:
        self._ttl = ttl_seconds
        self._entries: dict[tuple[object, ...], tuple[float, int | None]] = {}

    def get(self, key: tuple[object, ...]) -> tuple[bool, int | None]:
        entry = self._entries.get(key)
        if entry is None:
            return False, None
        expires, value = entry
        if _time.monotonic() >= expires:
            self._entries.pop(key, None)
            return False, None
        return True, value

    def set(self, key: tuple[object, ...], value: int | None) -> None:
        self._entries[key] = (_time.monotonic() + self._ttl, value)
        if len(self._entries) > 10_000:
            self._entries.clear()


_cache = BaselineCache()


def clear_baseline_cache() -> None:
    """Vacía la caché de baselines (pruebas / recálculo forzado)."""
    global _cache
    _cache = BaselineCache()


# =============================================================================
# Resolución de baselines desde PostgreSQL
# =============================================================================


def _day_bounds_utc(day: date, tz: ZoneInfo) -> tuple[datetime, datetime]:
    """Devuelve [inicio, fin) del día ``day`` en la zona canónica, convertidos a UTC."""
    start = datetime.combine(day, time.min, tzinfo=tz)
    return start.astimezone(timezone.utc), (start + timedelta(days=1)).astimezone(timezone.utc)


def _tramo_boundary_utc(as_of: datetime, tz: ZoneInfo) -> datetime:
    """Hora de ``as_of`` en la zona canónica, truncada a la hora y convertida a UTC."""
    local = as_of.astimezone(tz)
    return datetime.combine(local.date(), time(local.hour, 0), tzinfo=tz).astimezone(timezone.utc)


async def _resolve_kpi_baseline(
    session: AsyncSession,
    kpi_id: str,
    data_date: date,
    as_of: datetime,
) -> int | None:
    """Resuelve el baseline ``ayer_mismo_tramo`` de un KPI.

    Busca el último bucket horario de ayer (en la zona canónica) con hora ≤ la
    hora de ``as_of``; si no hay datos horarios, degrada al agregado diario de
    ayer (aproximación ``ayer_completo``) y, si nada, devuelve ``None``.
    """
    tz = canonical_tz()
    yesterday = data_date - timedelta(days=1)
    start_utc, end_utc = _day_bounds_utc(yesterday, tz)
    boundary = _tramo_boundary_utc(as_of, tz)

    stmt = (
        select(agg_hourly.c.value)
        .where(
            agg_hourly.c.kpi_id == kpi_id,
            agg_hourly.c.unidad_id == "",
            agg_hourly.c.turno_id == "",
            agg_hourly.c.bucket >= start_utc,
            agg_hourly.c.bucket < end_utc,
            agg_hourly.c.bucket <= boundary,
        )
        .order_by(agg_hourly.c.bucket.desc())
        .limit(1)
    )
    hourly = (await session.execute(stmt)).scalar_one_or_none()
    if hourly is not None:
        return int(hourly)

    daily: Any = (
        await session.execute(
            select(agg_daily.c.value)
            .where(
                agg_daily.c.bucket == yesterday,
                agg_daily.c.kpi_id == kpi_id,
                agg_daily.c.unidad_id == "",
                agg_daily.c.turno_id == "",
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return int(daily) if daily is not None else None


async def _resolve_turno_baseline(
    session: AsyncSession,
    turno_id: str,
    data_date: date,
) -> int | None:
    """Resuelve el baseline ``ayer_mismo_turno`` de un turno operativo."""
    yesterday = data_date - timedelta(days=1)
    value: Any = (
        await session.execute(
            select(agg_daily.c.value)
            .where(
                agg_daily.c.bucket == yesterday,
                agg_daily.c.kpi_id == "intervenciones",
                agg_daily.c.unidad_id == "",
                agg_daily.c.turno_id == turno_id,
            )
            .limit(1)
        )
    ).scalar_one_or_none()
    return int(value) if value is not None else None


# =============================================================================
# Cálculo de variación
# =============================================================================


def _direction(delta_abs: int) -> str:
    """Deriva la dirección a partir del delta absoluto (nunca del porcentaje)."""
    if delta_abs > 0:
        return "up"
    if delta_abs < 0:
        return "down"
    return "flat"


def compute_kpi_variation(value: int, baseline: int | None) -> dict[str, Any]:
    """Calcula ``delta_abs``/``delta_pct``/``direction``/``baseline_value``/``has_reference``.

    Sigue exactamente las reglas de §7.3 (ver docstring del módulo).
    """
    if baseline is None:
        return {
            "delta_abs": None,
            "delta_pct": None,
            "direction": "flat",
            "baseline_value": 0,
            "has_reference": False,
        }
    delta_abs = value - baseline
    if baseline == 0:
        return {
            "delta_abs": value,
            "delta_pct": None,
            "direction": _direction(delta_abs),
            "baseline_value": baseline,
            "has_reference": True,
        }
    delta_pct = round((delta_abs / baseline) * 100, 2)
    return {
        "delta_abs": delta_abs,
        "delta_pct": delta_pct,
        "direction": _direction(delta_abs),
        "baseline_value": baseline,
        "has_reference": True,
    }


# =============================================================================
# Enriquecimiento del payload (recalculo autoritativo de "vs ayer")
# =============================================================================


async def enrich_payload(
    session: AsyncSession,
    payload: dict[str, Any],
    *,
    data_date: date,
    as_of: datetime,
) -> dict[str, Any]:
    """Reescribe el payload con la variación calculada en el backend.

    - KPIs: recalcula ``delta_abs``/``delta_pct``/``direction``/``baseline_value``/
      ``has_reference`` con base ``ayer_mismo_tramo``.
    - Turnos: recalcula ``variacion_abs``/``variacion_pct`` con base
      ``ayer_mismo_turno`` (si no hay baseline, conserva el *hint* del agente).
    - Regional/ranking: se conservan tal cual (el agente los aporta; T33 no los
      recalcula).

    Devuelve una **copia** del payload (no muta el documento almacenado).
    """
    enriched = copy.deepcopy(payload)
    as_of = as_of.astimezone(timezone.utc)

    kpis = enriched.get("kpis") or {}
    for kpi_id in KPIS:
        if not isinstance(kpis.get(kpi_id), dict):
            continue
        value = int(kpis[kpi_id]["value"])
        cache_key: tuple[object, ...] = ("kpi", kpi_id, data_date, as_of.strftime("%Y-%m-%dT%H"))
        hit, baseline = _cache.get(cache_key)
        if not hit:
            baseline = await _resolve_kpi_baseline(session, kpi_id, data_date, as_of)
            _cache.set(cache_key, baseline)
        variation = compute_kpi_variation(value, baseline)
        kpis[kpi_id].update(
            {
                "delta_abs": variation["delta_abs"],
                "delta_pct": variation["delta_pct"],
                "direction": variation["direction"],
                "comparison": "ayer_mismo_tramo",
                "baseline_value": variation["baseline_value"],
                "as_of": as_of.isoformat(),
                "has_reference": variation["has_reference"],
            }
        )

    turnos = enriched.get("turnos") or []
    for item in turnos:
        if not isinstance(item, dict):
            continue
        turno_id = str(item.get("turno_id") or "")
        if turno_id not in TURNOS:
            continue
        cache_key = ("turno", turno_id, data_date)
        hit, baseline = _cache.get(cache_key)
        if not hit:
            baseline = await _resolve_turno_baseline(session, turno_id, data_date)
            _cache.set(cache_key, baseline)
        if baseline is not None:
            value = int(item["intervenciones"])
            delta_abs = value - baseline
            delta_pct = round((delta_abs / baseline) * 100, 2) if baseline else 0.0
            item["variacion_abs"] = delta_abs
            item["variacion_pct"] = delta_pct

    return enriched
