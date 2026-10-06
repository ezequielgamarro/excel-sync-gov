#!/usr/bin/env python3
"""Valida los ejemplos de `contracts/messages/*.example.json` contra su schema.

Cada `<version>.example.json` debe cumplir `<version>.schema.json` (spec §7.8:
"CI valida que el ejemplo cumple el esquema").

Ejecutable en local y en CI (job `contracts-validate`):

    python scripts/validate_contract_messages.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    from jsonschema import Draft202012Validator
except ImportError as exc:  # pragma: no cover - dependencia de CI/local
    print(
        "Falta la dependencia 'jsonschema'. Instálala con: pip install jsonschema",
        file=sys.stderr,
    )
    raise SystemExit(2) from exc

MESSAGES_DIR = Path(__file__).resolve().parent.parent / "contracts" / "messages"


def load(path: Path) -> object:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def main() -> int:
    schema_paths = sorted(MESSAGES_DIR.glob("*.schema.json"))
    if not schema_paths:
        print(f"No se encontraron schemas en {MESSAGES_DIR}", file=sys.stderr)
        return 1

    failures: list[str] = []
    checked = 0
    for schema_path in schema_paths:
        version = schema_path.name[: -len(".schema.json")]
        example_path = MESSAGES_DIR / f"{version}.example.json"
        if not example_path.exists():
            failures.append(f"{example_path.name}: falta el ejemplo para {schema_path.name}")
            continue

        schema = load(schema_path)
        example = load(example_path)
        validator = Draft202012Validator(schema)
        errors = sorted(
            validator.iter_errors(example),
            key=lambda error: [str(part) for part in error.absolute_path],
        )
        if errors:
            for error in errors:
                location = "$" + "".join(f"[{part!r}]" for part in error.absolute_path)
                failures.append(f"{example_path.name}{location}: {error.message}")
        else:
            print(f"OK  {example_path.name} cumple {schema_path.name}")
        checked += 1

    if failures:
        print("\nFallos de validación:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1

    print(f"\n{checked} ejemplo(s) validado(s) contra su schema.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
