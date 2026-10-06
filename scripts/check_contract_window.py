"""Verifica la ventana de soporte de 2 minors del contrato de mensajes (§7.8, T75).

El backend soporta y publica las **dos últimas minors** del cliente en
coexistencia durante los despliegues; la SPA se despliega **antes** que el
backend. Este script comprueba, sobre los schemas publicados en
``contracts/messages/``, que:

1. Cada versión es semver válido ``MAJOR.MINOR.PATCH``.
2. Dentro del major más reciente, las minors conservadas son contiguas y no
   exceden **2** (la vigente y la anterior). Más de 2 indica que se retuvieron
   minors fuera de la ventana de soporte.
3. Existe exactamente un schema con la minor más alta (la vigente).

Se ejecuta en CI (job ``test``) y devuelve 0 si la ventana es válida.

Uso::

    py scripts/check_contract_window.py

Sin dependencias externas.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MESSAGES_DIR = ROOT / "contracts" / "messages"

SEMVER_RE = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
SCHEMA_RE = re.compile(r"^(\d+\.\d+\.\d+)\.schema\.json$")

#: Número máximo de minors en coexistencia (§7.8: "dos últimas minors").
MAX_MINORS_IN_WINDOW = 2


def _versions() -> list[tuple[int, int, int]]:
    versions: list[tuple[int, int, int]] = []
    if not MESSAGES_DIR.is_dir():
        return versions
    for path in sorted(MESSAGES_DIR.iterdir()):
        match = SCHEMA_RE.match(path.name)
        if match is None:
            continue
        semver = SEMVER_RE.match(match.group(1))
        if semver is None:
            print(f"ERROR: nombre de schema no semver: {path.name}")
            raise SystemExit(1)
        versions.append((int(semver.group(1)), int(semver.group(2)), int(semver.group(3))))
    return versions


def main() -> int:
    versions = _versions()
    if not versions:
        print("ERROR: no hay schemas en contracts/messages/*.schema.json")
        return 1

    latest_major = max(major for major, _, _ in versions)
    minors = sorted({minor for major, minor, _ in versions if major == latest_major})
    span = minors[-1] - minors[0] + 1

    print(f"major vigente={latest_major} minors conservadas={minors} ventana={span}")

    errors: list[str] = []
    if len(minors) != span:
        errors.append(f"las minors del major {latest_major} no son contiguas: {minors}")
    if len(minors) > MAX_MINORS_IN_WINDOW:
        errors.append(
            f"hay {len(minors)} minors del major {latest_major} (máximo {MAX_MINORS_IN_WINDOW}); "
            "retirar las que quedan fuera de la ventana de 2 minors"
        )

    patches = [patch for major, minor, patch in versions if major == latest_major and minor == minors[-1]]
    if not patches:
        errors.append(f"no hay schema de la minor vigente {latest_major}.{minors[-1]}")

    if errors:
        for error in errors:
            print(f"FALLA: {error}")
        return 1

    print("OK: ventana de contrato válida (2 minors).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
