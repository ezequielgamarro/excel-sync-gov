"""Reasigna los roles de un usuario local existente (auth nativa JWT, §2.2.3).

``scripts/create_admin.py`` es idempotente: si el usuario ya existe no modifica
nada, por lo que no permite corregir su rol. Este script reemplaza por completo
la lista de roles de un usuario existente reutilizando la misma lógica de negocio
que la API (``user_store.set_roles``), con validación de roles conocidos.

Recuerda: por diseño (§2.2.3) el rol ``platform-admin`` **no** tiene
``dash.view.live``, así que un operador que deba ver el dashboard necesita el rol
``viewer`` o ``supervisor``.

Uso (desde ``backend/``)::

    python -m scripts.set_user_roles --username <u> --role supervisor
    python -m scripts.set_user_roles --username <u> --roles viewer,supervisor

Es idempotente: fija exactamente los roles indicados. ``DATABASE_URL`` se lee del
entorno (nunca se hardcodea, RNF-13).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

from app.core.errors import APIError
from app.services.db import dispose_engine, get_session
from app.services.user_store import (
    get_user_by_username,
    known_roles,
    roles_for_user,
    set_roles,
)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reemplaza los roles de un usuario local existente."
    )
    parser.add_argument("--username", required=True, help="Nombre de usuario.")
    parser.add_argument(
        "--role",
        action="append",
        dest="role",
        default=None,
        help="Rol a asignar (repetible). Ej.: --role viewer --role supervisor.",
    )
    parser.add_argument(
        "--roles",
        default=None,
        help="Lista de roles separada por comas. Ej.: --roles viewer,supervisor.",
    )
    return parser.parse_args(argv)


def _collect_roles(args: argparse.Namespace) -> list[str]:
    roles: list[str] = []
    if args.role:
        roles.extend(args.role)
    if args.roles:
        roles.extend(part for part in args.roles.split(","))
    return [role for role in (role.strip() for role in roles) if role]


def _user_id(row: Any) -> Any:
    return getattr(row, "_mapping", row)["user_id"]


async def _run(username: str, roles: list[str]) -> int:
    valid = known_roles()
    if not roles:
        print(
            "Error: indique al menos un rol con --role o --roles.",
            file=sys.stderr,
        )
        return 1
    unknown = sorted(set(roles) - valid)
    if unknown:
        print(
            f"Error: rol(es) desconocido(s): {', '.join(unknown)}. "
            f"Roles válidos: {', '.join(sorted(valid))}.",
            file=sys.stderr,
        )
        return 1

    session = await get_session()
    try:
        existing = await get_user_by_username(session, username)
        if existing is None:
            print(f"Error: el usuario '{username}' no existe.", file=sys.stderr)
            return 1
        user_id = _user_id(existing)
        await set_roles(session, user_id, roles)
        await session.commit()
        result = await roles_for_user(session, user_id)
        print(f"Roles de '{username}' actualizados: {result}.")
        return 0
    except APIError as exc:
        print(f"Error: {exc.message}", file=sys.stderr)
        return 1
    finally:
        await session.close()
        await dispose_engine()


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    roles = _collect_roles(args)
    return asyncio.run(_run(args.username, roles))


if __name__ == "__main__":
    raise SystemExit(main())
