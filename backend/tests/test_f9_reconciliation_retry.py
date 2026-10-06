"""T65 — Reintentos con backoff y reconciliación de respaldo (CA-01.7, RF-01.i/j,
RNF-06.f).

Verifica la política verificable sin ejecutar el origen ni el job:

- El backoff del webhook es ``2, 4, 8, 16, 32, 60`` s con jitter ±20 % (Apps
  Script, `00_config.gs`).
- El backend reconcilia por polling de respaldo cada 60 s y conserva el umbral
  de degradación de 15 min (config).
- La reconciliación compara el ``content_sha256`` con el último aceptado y no
  descarta datos (el origen persiste el hash/estado pendiente).

Directamente::

    py backend/tests/test_f9_reconciliation_retry.py
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]

_APPS_CONFIG = (_REPO / "apps-script" / "00_config.gs").read_text(encoding="utf-8")
_BACKEND_CONFIG = (_REPO / "backend" / "app" / "config.py").read_text(encoding="utf-8")
_RECONCILIATION = (_REPO / "backend" / "app" / "services" / "reconciliation.py").read_text(
    encoding="utf-8"
)
_SOURCE_HEALTH = (_REPO / "backend" / "app" / "services" / "source_health.py").read_text(
    encoding="utf-8"
)


def test_backoff_sequence_and_jitter() -> None:
    match = re.search(r"BACKOFF_SECONDS:\s*\[([^\]]+)\]", _APPS_CONFIG)
    assert match is not None
    values = [int(value.strip()) for value in match.group(1).split(",")]
    assert values == [2, 4, 8, 16, 32, 60]
    assert "JITTER_RATIO: 0.2" in _APPS_CONFIG


def test_reconciliation_polling_interval_is_60s() -> None:
    assert "reconciliation_interval_seconds: int = 60" in _BACKEND_CONFIG
    # El job de respaldo compara el hash de contenido y reutiliza la ingesta.
    assert "content_sha256" in _RECONCILIATION
    assert "persist_webhook" in _RECONCILIATION


def test_source_degraded_threshold_is_15_minutes() -> None:
    assert "source_degraded_threshold_seconds: int = 900" in _BACKEND_CONFIG
    assert "degraded" in _SOURCE_HEALTH


def test_origin_persists_state_without_discarding_data() -> None:
    # El Apps Script marca el envío pendiente y el hash exitoso; nunca descarta.
    assert "PENDING_SEND" in _APPS_CONFIG
    assert "LAST_SUCCESS_HASH" in _APPS_CONFIG


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
            except Exception as exc:  # noqa: BLE001
                failures += 1
                print(f"FAIL {name}: {exc}")
            else:
                print(f"PASS {name}")
    if failures:
        raise SystemExit(1)
    print("OK")
