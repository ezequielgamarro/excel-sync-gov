"""Hashing fuerte de contraseñas y política local (spec §2.2.2, RNF-03.a, T34).

Autenticación **nativa**: el backend custodia las credenciales de los operadores
en ``app.user_account``. Las contraseñas se almacenan **siempre** como hash
**Argon2id** (sal por usuario y parámetros de coste); nunca en claro y nunca en
logs. Sin segundo factor ni reautenticación por acción.

La dependencia ``argon2-cffi`` se importa de forma perezosa para poder probar la
política de contraseñas en entornos sin el paquete. La verificación es en tiempo
constante (delegada en Argon2).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# Parámetros de coste Argon2id (razonables para servidor; ajustables en despliegue).
_TIME_COST = 3
_MEMORY_COST_KIB = 65536  # 64 MiB
_PARALLELISM = 2
_HASH_LEN = 32
_SALT_LEN = 16

_SPECIALS = re.compile(r"[^A-Za-z0-9]")


class PasswordPolicyError(ValueError):
    """La contraseña no cumple la política mínima del sistema."""


@dataclass(frozen=True)
class PasswordPolicy:
    """Política mínima de contraseñas (longitud + complejidad, §2.2.2)."""

    min_length: int = 12
    require_complexity: bool = True


def validate_password_policy(password: str, policy: PasswordPolicy) -> None:
    """Valida la política mínima; lanza ``PasswordPolicyError`` si no cumple.

    - Longitud mínima configurable.
    - Complejidad: al menos una letra, un dígito y un carácter no alfanumérico
      (cuando ``require_complexity`` está activo).
    """
    if not isinstance(password, str) or len(password) < policy.min_length:
        raise PasswordPolicyError(
            f"La contraseña debe tener al menos {policy.min_length} caracteres."
        )
    if policy.require_complexity:
        if not re.search(r"[A-Za-z]", password):
            raise PasswordPolicyError("La contraseña debe incluir al menos una letra.")
        if not re.search(r"\d", password):
            raise PasswordPolicyError("La contraseña debe incluir al menos un dígito.")
        if not _SPECIALS.search(password):
            raise PasswordPolicyError(
                "La contraseña debe incluir al menos un carácter especial."
            )


def hash_password(password: str) -> str:
    """Devuelve el hash Argon2id de ``password`` (sal por usuario)."""
    try:
        from argon2 import PasswordHasher
        from argon2.low_level import Type
    except Exception as exc:  # pragma: no cover - dependencia no instalada
        raise RuntimeError("argon2-cffi no está disponible para hashear contraseñas.") from exc

    hasher = PasswordHasher(
        time_cost=_TIME_COST,
        memory_cost=_MEMORY_COST_KIB,
        parallelism=_PARALLELISM,
        hash_len=_HASH_LEN,
        salt_len=_SALT_LEN,
        type=Type.ID,
    )
    return hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """Verifica ``password`` contra un hash Argon2id (tiempo constante)."""
    if not password_hash or not password:
        return False
    try:
        from argon2 import PasswordHasher
        from argon2.exceptions import InvalidHashError, VerifyMismatchError
    except Exception:  # pragma: no cover - dependencia no instalada
        return False
    hasher = PasswordHasher(
        time_cost=_TIME_COST,
        memory_cost=_MEMORY_COST_KIB,
        parallelism=_PARALLELISM,
        hash_len=_HASH_LEN,
        salt_len=_SALT_LEN,
    )
    try:
        return hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False
    except Exception:  # pragma: no cover - hash corrupto/parámetros inválidos
        return False
