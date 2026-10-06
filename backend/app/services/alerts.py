"""Alertas configurables y evaluación de umbrales (spec RNF-07.d, T60).

Reglas exigidas por RNF-07.d:

==============================  ===============================================
Regla                           Umbral (configurable en ``Settings``)
==============================  ===============================================
``latency_p95_high``            p95 de latencia de ingesta > 2 s
``rejection_rate_high``         tasa de rechazo (4xx/5xx) > 1 %
``wss_zero_active_room``        conexiones WSS a 0 con sala activa
``webhook_stale``               último webhook > 5 min
``webhook_retries_exhausted``   reintentos de webhook agotados > 0
``payload_too_large``           payload > 64 KB
``sql_debounce_high``           debounce de SQL > 1 %
==============================  ===============================================

La evaluación es **sin estado** sobre una foto de métricas
(:class:`MetricsSnapshot`); :class:`AlertRegistry` recuerda las transiciones,
publica la métrica Prometheus ``alert_active`` y puede auditar
``alert.raised``/``alert.resolved``. Las métricas se leen del registro de
Prometheus y la salud del origen se inyecta desde la capa de servicios, de modo
que este módulo no depende de la BD.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from app.config import Settings, get_settings
from app.core.logging import get_logger
from app.core.metrics import ALERT_ACTIVE, INGEST_MAX_PAYLOAD_BYTES, SQL_DEBOUNCE_RATIO

logger = get_logger(__name__)

SEVERITY_WARNING = "warning"
SEVERITY_CRITICAL = "critical"

ACTION_ALERT_RAISED = "alert.raised"
ACTION_ALERT_RESOLVED = "alert.resolved"


@dataclass(frozen=True)
class AlertRule:
    """Regla de alerta: métrica, comparador, umbral y severidad."""

    name: str
    metric: str
    comparator: str  # "gt" | "gte" | "lte"
    threshold: float
    severity: str
    description: str

    def triggered(self, value: float | None) -> bool:
        """``True`` si la regla se dispara con ``value`` (``None`` no dispara)."""
        if value is None:
            return False
        if self.comparator == "gt":
            return value > self.threshold
        if self.comparator == "lte":
            return value <= self.threshold
        return value >= self.threshold


@dataclass
class MetricsSnapshot:
    """Foto de las métricas que alimentan las reglas (RNF-07.d)."""

    ingest_latency_p95_seconds: float | None = None
    rejection_rate: float | None = None
    wss_connections_active: int | None = None
    room_active: bool = False
    webhook_seconds_since_last: float | None = None
    webhook_retries_exhausted: int | None = None
    max_payload_bytes: int | None = None
    sql_debounce_rate: float | None = None

    def value_for(self, metric: str) -> float | None:
        return getattr(self, metric, None)  # type: ignore[no-any-return]


@dataclass(frozen=True)
class Alert:
    """Alerta evaluada (una regla disparada)."""

    name: str
    severity: str
    metric: str
    value: float
    threshold: float
    description: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "severity": self.severity,
            "metric": self.metric,
            "value": self.value,
            "threshold": self.threshold,
            "description": self.description,
        }


def default_rules(settings: Settings) -> list[AlertRule]:
    """Catálogo por defecto de reglas, parametrizado por ``Settings`` (RNF-07.d)."""
    return [
        AlertRule(
            name="latency_p95_high",
            metric="ingest_latency_p95_seconds",
            comparator="gt",
            threshold=settings.alert_latency_p95_seconds,
            severity=SEVERITY_CRITICAL,
            description="p95 de latencia de ingesta > 2 s (10 min).",
        ),
        AlertRule(
            name="rejection_rate_high",
            metric="rejection_rate",
            comparator="gt",
            threshold=settings.alert_rejection_rate,
            severity=SEVERITY_WARNING,
            description="Tasa de rechazo (4xx/5xx) > 1 %.",
        ),
        AlertRule(
            name="wss_zero_active_room",
            metric="wss_connections_active",
            comparator="lte",
            threshold=0.0,
            severity=SEVERITY_CRITICAL,
            description="Conexiones WSS a 0 con sala activa.",
        ),
        AlertRule(
            name="webhook_stale",
            metric="webhook_seconds_since_last",
            comparator="gt",
            threshold=float(settings.alert_webhook_stale_seconds),
            severity=SEVERITY_WARNING,
            description="Último webhook supera 5 min.",
        ),
        AlertRule(
            name="webhook_retries_exhausted",
            metric="webhook_retries_exhausted",
            comparator="gt",
            threshold=0.0,
            severity=SEVERITY_CRITICAL,
            description="Reintentos de webhook agotados.",
        ),
        AlertRule(
            name="payload_too_large",
            metric="max_payload_bytes",
            comparator="gt",
            threshold=float(settings.alert_payload_max_bytes),
            severity=SEVERITY_WARNING,
            description="Payload de ingesta > 64 KB.",
        ),
        AlertRule(
            name="sql_debounce_high",
            metric="sql_debounce_rate",
            comparator="gt",
            threshold=settings.alert_sql_debounce_rate,
            severity=SEVERITY_WARNING,
            description="Debounce de SQL > 1 %.",
        ),
    ]


def evaluate_alerts(snapshot: MetricsSnapshot, rules: list[AlertRule]) -> list[Alert]:
    """Evalúa todas las reglas sobre la foto y devuelve las disparadas."""
    active: list[Alert] = []
    for rule in rules:
        value = snapshot.value_for(rule.metric)
        if value is None or not rule.triggered(float(value)):
            continue
        active.append(
            Alert(
                name=rule.name,
                severity=rule.severity,
                metric=rule.metric,
                value=float(value),
                threshold=rule.threshold,
                description=rule.description,
            )
        )
    return active


class AlertRegistry:
    """Sigue el ciclo de vida de las alertas y publica la métrica ``alert_active``."""

    def __init__(
        self,
        rules: list[AlertRule] | None = None,
        *,
        on_transition: Callable[[str, Alert], Any] | None = None,
    ) -> None:
        self._rules = rules if rules is not None else default_rules(get_settings())
        self._active: dict[str, Alert] = {}
        self._on_transition = on_transition

    @property
    def rules(self) -> list[AlertRule]:
        return list(self._rules)

    @property
    def active(self) -> list[Alert]:
        return list(self._active.values())

    def set_transition_callback(self, callback: Callable[[str, Alert], Any] | None) -> None:
        self._on_transition = callback

    def evaluate(self, snapshot: MetricsSnapshot) -> list[Alert]:
        """Evalúa y actualiza el estado; registra y publica las transiciones."""
        triggered = {alert.name: alert for alert in evaluate_alerts(snapshot, self._rules)}

        # Nuevas alertas.
        for name, alert in triggered.items():
            if name not in self._active:
                self._record_transition(ACTION_ALERT_RAISED, alert)
        # Alertas resueltas.
        for name in list(self._active):
            if name not in triggered:
                resolved = self._active.pop(name)
                self._record_transition(ACTION_ALERT_RESOLVED, resolved)

        self._active = triggered
        self._publish_gauges()
        return list(triggered.values())

    def _publish_gauges(self) -> None:
        for rule in self._rules:
            value = 1.0 if rule.name in self._active else 0.0
            ALERT_ACTIVE.labels(rule=rule.name, severity=rule.severity).set(value)

    def _record_transition(self, action: str, alert: Alert) -> None:
        logger.warning(
            action,
            extra={
                "event": "alert",
                "action": action,
                "result": alert.name,
                "status_code": int(alert.value),
            },
        )
        callback = self._on_transition
        if callback is None:
            return
        try:
            callback(action, alert)
        except Exception:  # pragma: no cover - la alerta no debe tumbar la petición
            pass


# =============================================================================
# Lectura de métricas Prometheus (RNF-07.d)
# =============================================================================
def _iter_samples() -> list[tuple[str, dict[str, str], float]]:
    from prometheus_client import REGISTRY

    samples: list[tuple[str, dict[str, str], float]] = []
    for metric in REGISTRY.collect():
        for sample in metric.samples:
            samples.append((sample.name, dict(sample.labels), float(sample.value)))
    return samples


def _count_sum(name: str) -> float:
    for sample_name, _labels, value in _iter_samples():
        if sample_name == name:
            return value
    return 0.0


def _histogram_quantile(name: str, quantile: float, label_filter: str = "") -> float | None:
    """Cuenta el cuantil ``quantile`` (0..1) de un histograma Prometheus.

    Implementa el algoritmo estándar ``histogram_quantile`` agregando los buckets
    ``<name>_bucket`` (opcionalmente filtrando por subcadena de ruta), sin requerir
    un servidor Prometheus.
    """
    buckets: dict[float, float] = {}
    total_count = 0.0
    found = False
    for sample_name, labels, value in _iter_samples():
        if sample_name != f"{name}_bucket":
            continue
        if label_filter and label_filter not in labels.get("path", ""):
            continue
        found = True
        try:
            le = float(labels.get("le", "inf"))
        except ValueError:
            continue
        buckets[le] = buckets.get(le, 0.0) + value
        if le == float("inf"):
            total_count += value
    if not found or total_count <= 0:
        return None
    if quantile <= 0:
        return 0.0
    rank = quantile * total_count
    previous_le = 0.0
    previous_cumulative = 0.0
    for le in sorted(buckets):
        cumulative = buckets[le]
        if cumulative >= rank:
            if le == float("inf"):
                return previous_le
            span = le - previous_le
            fraction = (rank - previous_cumulative) / (cumulative - previous_cumulative)
            return previous_le + span * fraction
        previous_le = le
        previous_cumulative = cumulative
    return previous_le


def _wss_connections() -> int | None:
    total = 0
    seen = False
    for sample_name, _labels, value in _iter_samples():
        if sample_name == "wss_connections":
            total += int(value)
            seen = True
    return total if seen else None


def _max_payload_bytes() -> int | None:
    """Mayor payload de ingesta observado (gauge ``ingest_max_payload_bytes``)."""
    value = INGEST_MAX_PAYLOAD_BYTES._value.get()  # type: ignore[attr-defined]
    return int(value) if value and value > 0 else None


def collect_metrics_snapshot(
    *,
    settings: Settings | None = None,
    wss_connections_active: int | None = None,
    room_active: bool = False,
    webhook_seconds_since_last: float | None = None,
    webhook_retries_exhausted: int | None = None,
    sql_debounce_rate: float | None = None,
) -> MetricsSnapshot:
    """Compone la foto de métricas del registro Prometheus + señales externas.

    ``webhook_seconds_since_last``, ``webhook_retries_exhausted`` y
    ``sql_debounce_rate`` se inyectan desde las capas que tienen acceso a la BD /
    gauges; el resto se lee del registro de Prometheus.
    """
    if wss_connections_active is None:
        wss_connections_active = _wss_connections()
    # La regla "WSS a 0 con sala activa" solo aplica con sala activa: sin sala,
    # la señal se anula para no disparar la alerta (RNF-07.d).
    if not room_active:
        wss_connections_active = None
    if sql_debounce_rate is None:
        sql_debounce_rate = SQL_DEBOUNCE_RATIO._value.get()  # type: ignore[attr-defined]
    total = _count_sum("http_requests_total")
    rejections = _count_sum("http_responses_4xx_5xx_total")
    rejection_rate = (rejections / total) if total > 0 else None
    return MetricsSnapshot(
        ingest_latency_p95_seconds=_histogram_quantile(
            "http_request_duration_seconds", 0.95, label_filter="ingest"
        ),
        rejection_rate=rejection_rate,
        wss_connections_active=wss_connections_active,
        room_active=room_active,
        webhook_seconds_since_last=webhook_seconds_since_last,
        webhook_retries_exhausted=webhook_retries_exhausted,
        max_payload_bytes=_max_payload_bytes(),
        sql_debounce_rate=sql_debounce_rate,
    )


_registry: AlertRegistry | None = None


def get_alert_registry() -> AlertRegistry:
    """Registro de alertas compartido (singleton por proceso)."""
    global _registry
    if _registry is None:
        _registry = AlertRegistry(default_rules(get_settings()))
    return _registry


def reset_alert_registry() -> None:
    """Reinicia el registro de alertas (pruebas/arranque)."""
    global _registry
    _registry = None


def utc_now() -> datetime:
    """Instante actual en UTC (helper de trazabilidad de la evaluación)."""
    return datetime.now(timezone.utc)
