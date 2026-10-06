"""Verificación de ausencia de PII y secretos en código/logs (RNF-08.c, RNF-13, T64).

Complementa a ``gitleaks`` (CI) con una comprobación *en árbol de trabajo* que:

1. **Secretos hardcodeados**: detecta asignaciones con material plausible en
   código/plantillas (excluyendo ``specs/**`` y ``.env.example``, que solo llevan
   nombres). Los placeholders conocidos (``changeme``, ``example``, ``<...>``,
   ``${...}``, vacío) no cuentan.
2. **PII en logs**: detecta llamadas de logging que volcarían payloads, celdas,
   filas, contraseñas o secretos (RNF-08.c).
3. **Diseño obsoleto**: referencias a ``Keycloak``/``OIDC`` que no sean una
   negación explícita ("sin ...", "no hay ...", "desacoplado").

Uso::

    py scripts/scan_pii_secrets.py        # exit 1 si hay hallazgos

Salida: una línea por hallazgo (ruta:línea: motivo). Sin dependencias externas.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

SCAN_DIRS = [
    ROOT / "backend" / "app",
    ROOT / "backend" / "alembic",
    ROOT / "backend" / "tests",
    ROOT / "backend" / "docs",
    ROOT / "apps-script",
    ROOT / "dashboard" / "src",
    ROOT / "dashboard" / "public",
    ROOT / "infra",
    ROOT / "scripts",
    ROOT / ".github",
]
SCAN_FILES = [
    ROOT / "pyproject.toml",
    ROOT / "README.md",
    ROOT / "backend" / "README.md",
]
SKIP_DIRS = {"node_modules", "__pycache__", ".git", "dist", "build", ".venv"}
TEXT_SUFFIXES = {
    ".py",
    ".gs",
    ".ts",
    ".tsx",
    ".js",
    ".mjs",
    ".cjs",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".md",
    ".tf",
    ".env",
    ".example",
    ".txt",
}

# --- Secretos hardcodeados ----------------------------------------------------
SECRET_KEY_RE = re.compile(
    r"(?i)\b(secret|password|passwd|signing_key|api[_-]?key|apikey|"
    r"kek_material|data_key|private_key|encryption_key|access_token)\b"
    r"\s*[:=]\s*[\"']([^\"']{8,})[\"']"
)
# Palabras que indican placeholder / nombre de variable, no un secreto real.
PLACEHOLDER_RE = re.compile(
    r"(?i)^(changeme|placeholder|example|your[-_]|<.*>|\$\{.*\}|none|null|"
    r"test[-_]?only|dummy|redacted|xxx+|\*+|test[-_]secret.*|not[-_]a[-_]real.*|"
    r".*clave.*|.*fake.*|.*sample.*|.*prueba.*)$"
)
# Una asignación vacía o un nombre en UPPER_SNAKE (referencia a variable de entorno).
ENV_NAME_RE = re.compile(r"^[A-Z][A-Z0-9_]{3,}$")

# --- PII / volcado en logs ----------------------------------------------------
LOG_CALL_RE = re.compile(r"(?i)\b(logger|logging|log)\.\w+\s*\(")
PII_IN_LOG_RE = re.compile(
    r"(?i)(payload|plaintext|ciphertext|celda|cell|rows?\b|fila|password|passwd|"
    r"secret|token|authorization|cookie|documento|document\b|raw[_ ]?body)"
)

# --- Diseño obsoleto ----------------------------------------------------------
OBSOLETE_DESIGN_RE = re.compile(r"(?i)(keycloak|oidc)")
NEGATION_RE = re.compile(
    r"(?i)(sin\s+\w*\s*(keycloak|oidc|idp)|no\s+hay|desacoplado|"
    r"excluye|queda fuera|retirad|antigu|antigua|pivote|migrad)"
)


def _iter_files():
    self_path = Path(__file__).resolve()
    for base in SCAN_DIRS:
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if not path.is_file():
                continue
            if path.resolve() == self_path:
                continue
            if any(part in SKIP_DIRS for part in path.parts):
                continue
            if path.suffix.lower() not in TEXT_SUFFIXES and path.name != ".env.example":
                continue
            yield path
    for path in SCAN_FILES:
        if path.exists():
            yield path


def _read(path: Path) -> list[str]:
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def scan() -> list[str]:
    findings: list[str] = []
    for path in _iter_files():
        for number, line in enumerate(_read(path), start=1):
            stripped = line.strip()
            if stripped.startswith("#") and "=" not in stripped:
                # Comentarios puros no introducen secretos.
                pass
            secret = SECRET_KEY_RE.search(line)
            if secret is not None:
                key, value = secret.group(1), secret.group(2)
                if (
                    not PLACEHOLDER_RE.match(value)
                    and not ENV_NAME_RE.match(value)
                    and "$" not in value
                ):
                    findings.append(
                        f"{path.relative_to(ROOT)}:{number}: posible secreto hardcodeado ({key})"
                    )
            if LOG_CALL_RE.search(line) and PII_IN_LOG_RE.search(line):
                findings.append(f"{path.relative_to(ROOT)}:{number}: posible PII/volcado en log")
            if OBSOLETE_DESIGN_RE.search(line) and not NEGATION_RE.search(line):
                findings.append(
                    f"{path.relative_to(ROOT)}:{number}: referencia a diseño obsoleto (IdP externo)"
                )
    return findings


def main() -> int:
    findings = scan()
    if not findings:
        print("OK: sin secretos, PII en logs ni diseño obsoleto en el árbol escaneado.")
        return 0
    for finding in findings:
        print(f"FINDING {finding}")
    print(f"\n{len(findings)} hallazgo(s).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
