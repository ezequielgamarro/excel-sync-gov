"""T71 — Cierre de la matriz de trazabilidad de los 40 CA (spec §15).

Verifica que `docs/traceability.md` cubre **todos** los criterios de aceptación
(CA-01.1 … CA-05.9) sin huecos y que cada fila mapea, como mínimo:

- una tarea F9 (T65–T70);
- un test automatizado (pytest/vitest/playwright/k6);
- el RF y el RNF asociados.

Directamente::

    py backend/tests/test_f9_traceability.py
"""

from __future__ import annotations

import re
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_DOC = _REPO / "docs" / "traceability.md"

_EXPECTED_CAS = {
    "CA-01.1", "CA-01.2", "CA-01.3", "CA-01.4", "CA-01.5", "CA-01.6", "CA-01.7", "CA-01.8",
    "CA-02.1", "CA-02.2", "CA-02.3", "CA-02.4", "CA-02.5", "CA-02.6", "CA-02.7", "CA-02.8",
    "CA-02.9", "CA-02.10",
    "CA-03.1", "CA-03.2", "CA-03.3", "CA-03.4", "CA-03.5", "CA-03.6",
    "CA-04.1", "CA-04.2", "CA-04.3", "CA-04.4", "CA-04.5", "CA-04.6", "CA-04.7",
    "CA-05.1", "CA-05.2", "CA-05.3", "CA-05.4", "CA-05.5", "CA-05.6", "CA-05.7", "CA-05.8",
    "CA-05.9",
}

_TASK_RE = re.compile(r"T6[5-9]|T70")
_TEST_RE = re.compile(r"test|spec", re.IGNORECASE)
_RF_RE = re.compile(r"RF-0[1-5]")
_RNF_RE = re.compile(r"RNF-\d+")


def _rows() -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {}
    for line in _DOC.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| CA-"):
            continue
        parts = [part.strip() for part in line.strip().strip("|").split("|")]
        rows[parts[0]] = parts
    return rows


def test_matrix_file_exists() -> None:
    assert _DOC.exists(), "falta docs/traceability.md (T71)"


def test_all_40_cas_present_without_duplicates() -> None:
    rows = _rows()
    assert set(rows) == _EXPECTED_CAS, sorted(_EXPECTED_CAS ^ set(rows))
    assert len(rows) == 40


def test_every_ca_maps_to_task_test_rf_and_rnf() -> None:
    missing: list[str] = []
    for ca, parts in _rows().items():
        # CA | Tarea | Test | RF | RNF | AM | Visual
        assert len(parts) >= 7, f"{ca}: columnas insuficientes ({len(parts)})"
        tasks, tests, rf, rnf = parts[1], parts[2], parts[3], parts[4]
        if not _TASK_RE.search(tasks):
            missing.append(f"{ca}: sin tarea F9 ({tasks})")
        if not _TEST_RE.search(tests):
            missing.append(f"{ca}: sin test ({tests})")
        if not _RF_RE.search(rf):
            missing.append(f"{ca}: sin RF ({rf})")
        if not _RNF_RE.search(rnf):
            missing.append(f"{ca}: sin RNF ({rnf})")
    assert not missing, "\n".join(missing)


def test_no_ca_is_gap() -> None:
    covered = set(_rows())
    assert _EXPECTED_CAS - covered == set()


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
