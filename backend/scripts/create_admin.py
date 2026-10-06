"""Bootstrap del primer usuario local (auth nativa JWT, §2.2.2, T34).

Los endpoints de administración de usuarios exigen estar ya autenticado, así que
el primer operador no puede crearse por API. Este script crea un usuario local
reutilizando exactamente la misma lógica de negocio que la API
(``user_store.create_user``: política de contraseñas, hash Argon2id y roles).

Uso (desde ``backend/``)::

    python -m scripts.create_admin --username <u> --password <p> [--role platform-admin]

Es un **upsert**: si el usuario no existe lo crea; si ya existe, actualiza su
contraseña (rotación) y sus roles reutilizando ``user_store.reset_password`` y
``user_store.update_user``. En ambos casos asigna el rol principal (``--role``,
por defecto ``platform-admin``) **más** el rol ``viewer``, que es el que otorga
``dash.view.live`` y permite ver el dashboard en vivo. ``DATABASE_URL`` se lee
del entorno (nunca se hardcodea, RNF-13).
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from app.core.errors import APIError
from app.services.db import dispose_engine, get_session
from app.services.passwords import PasswordPolicyError
from app.services.user_store import (
    create_user,
    get_user_by_username,
    reset_password,
    update_user,
)

DEFAULT_ROLE = "platform-admin"
DEFAULT_VIEWER_ROLE = "viewer"


def _roles_for(role: str) -> list[str]:
    return sorted({role, DEFAULT_VIEWER_ROLE})


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Crea el primer usuario local (bootstrap de auth nativa JWT)."
    )
    parser.add_argument("--username", required=True, help="Nombre de usuario.")
    parser.add_argument(
        "--password",
        required=True,
        help="Contraseña en claro (se hashea Argon2id; no se registra).",
    )
    parser.add_argument(
        "--role",
        default=DEFAULT_ROLE,
        help=f"Rol a asignar (por defecto: {DEFAULT_ROLE}).",
    )
    return parser.parse_args(argv)


async def _run(username: str, password: str, role: str) -> int:
    session = await get_session()
    try:
        existing = await get_user_by_username(session, username)
        if existing is None:
            user = await create_user(
                session, username=username, password=password, roles=_roles_for(role)
            )
            print(
                f"Usuario '{user['username']}' creado con roles {user['roles']} (id={user['id']})."
            )
            return 0
        user_id = getattr(existing, "_mapping", existing)["user_id"]
        await reset_password(session, user_id, password)
        await update_user(session, user_id, roles=_roles_for(role), enabled=True)
        print(
            f"Usuario '{username}' actualizado (upsert): contraseña rotada y "
            f"roles {_roles_for(role)}."
        )
        return 0
    except APIError as exc:
        print(f"Error: {exc.message}", file=sys.stderr)
        return 1
    except PasswordPolicyError as exc:
        print(f"Error de política de contraseña: {exc}", file=sys.stderr)
        return 1
    finally:
        await session.close()
        await dispose_engine()


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    return asyncio.run(_run(args.username, args.password, args.role))


if __name__ == "__main__":
    raise SystemExit(main())
