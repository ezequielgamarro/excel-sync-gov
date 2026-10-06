"""Almacén local de usuarios y refresh tokens en PostgreSQL (spec §2.2.2, T34/T36).

Authn **nativa**: los operadores viven en ``app.user_account`` (hash Argon2id,
estado, bloqueo por intentos) y su mapeo a roles en ``app.user_role``. El refresh
rotativo se persiste en ``app.refresh_token`` (cadena con detección de reuso).

Todas las consultas usan ``session.execute(...)``; no se registran contraseñas ni
hashes en logs (RNF-13).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.errors import raise_http_error
from app.models.tables import refresh_token, user_account, user_role
from app.services.jwt_native import ACTIVE, REVOKED, ROTATED, RefreshRecord
from app.services.passwords import (
    PasswordPolicy,
    hash_password,
    validate_password_policy,
)

_KNOWN_ROLES: frozenset[str] = frozenset(
    {"viewer", "supervisor", "auditor", "platform-admin"}
)


def known_roles() -> frozenset[str]:
    """Roles válidos del sistema (§2.2.3)."""
    return _KNOWN_ROLES


def _now() -> datetime:
    return datetime.now(timezone.utc)


def password_policy() -> PasswordPolicy:
    settings = get_settings()
    return PasswordPolicy(
        min_length=settings.password_min_length,
        require_complexity=settings.password_require_complexity,
    )


def _validate_new_password(password: str) -> str:
    validate_password_policy(password, password_policy())
    return hash_password(password)


# =============================================================================
# Lectura
# =============================================================================
async def get_user_by_username(session: AsyncSession, username: str) -> Any | None:
    result = await session.execute(
        select(user_account).where(func.lower(user_account.c.username) == username.strip().lower())
    )
    return result.first()


async def get_user_by_sub(session: AsyncSession, sub: str) -> Any | None:
    result = await session.execute(select(user_account).where(user_account.c.sub == sub))
    return result.first()


async def get_user_by_id(session: AsyncSession, user_id: str) -> Any | None:
    try:
        uid = uuid.UUID(user_id)
    except (ValueError, AttributeError, TypeError):
        return None
    result = await session.execute(select(user_account).where(user_account.c.user_id == uid))
    return result.first()


async def list_users(
    session: AsyncSession, *, search: str = "", limit: int = 100, offset: int = 0
) -> list[Any]:
    stmt = select(user_account).order_by(user_account.c.username).limit(limit).offset(offset)
    if search:
        stmt = stmt.where(func.lower(user_account.c.username).contains(search.strip().lower()))
    result = await session.execute(stmt)
    return list(result.all())


async def roles_for_user(session: AsyncSession, user_id: uuid.UUID) -> list[str]:
    result = await session.execute(
        select(user_role.c.role).where(user_role.c.user_id == user_id).order_by(user_role.c.role)
    )
    return [str(row[0]) for row in result.all()]


async def roles_for_sub(session: AsyncSession, sub: str) -> list[str]:
    result = await session.execute(
        select(user_role.c.role)
        .join(user_account, user_account.c.user_id == user_role.c.user_id)
        .where(user_account.c.sub == sub)
        .order_by(user_role.c.role)
    )
    return [str(row[0]) for row in result.all()]


# =============================================================================
# Escritura (altas/bajas/roles/estado)
# =============================================================================
def _validate_roles(roles: list[str]) -> list[str]:
    unknown = sorted(set(roles) - _KNOWN_ROLES)
    if unknown:
        raise_http_error("BAD_REQUEST", "Rol desconocido.")
    return sorted(set(roles))


async def set_roles(session: AsyncSession, user_id: uuid.UUID, roles: list[str]) -> None:
    valid = _validate_roles(roles)
    await session.execute(delete(user_role).where(user_role.c.user_id == user_id))
    if valid:
        now = _now()
        await session.execute(
            insert(user_role),
            [{"user_id": user_id, "role": role, "granted_at": now} for role in valid],
        )


async def create_user(
    session: AsyncSession, *, username: str, password: str, roles: list[str]
) -> dict[str, Any]:
    username = username.strip()
    if not username:
        raise_http_error("BAD_REQUEST", "Nombre de usuario requerido.")
    existing = await get_user_by_username(session, username)
    if existing is not None:
        raise_http_error("CONFLICT", "El usuario ya existe.", status_code=409)

    password_hash = _validate_new_password(password)
    user_id = uuid.uuid4()
    now = _now()
    await session.execute(
        insert(user_account).values(
            user_id=user_id,
            sub=str(user_id),
            username=username,
            password_hash=password_hash,
            estado="activo",
            failed_attempts=0,
            created_at=now,
            updated_at=now,
        )
    )
    await set_roles(session, user_id, roles)
    await session.commit()
    return {"id": str(user_id), "username": username, "roles": _validate_roles(roles)}


async def update_user(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    enabled: bool | None = None,
    roles: list[str] | None = None,
) -> None:
    values: dict[str, Any] = {"updated_at": _now()}
    if enabled is not None:
        values["estado"] = "activo" if enabled else "deshabilitado"
        values["disabled_at"] = None if enabled else _now()
        if enabled:
            values["failed_attempts"] = 0
            values["locked_until"] = None
    await session.execute(
        update(user_account).where(user_account.c.user_id == user_id).values(**values)
    )
    if roles is not None:
        await set_roles(session, user_id, roles)
    await session.commit()


async def disable_user(session: AsyncSession, user_id: uuid.UUID) -> None:
    await update_user(session, user_id, enabled=False)


async def reset_password(session: AsyncSession, user_id: uuid.UUID, password: str) -> None:
    password_hash = _validate_new_password(password)
    await session.execute(
        update(user_account)
        .where(user_account.c.user_id == user_id)
        .values(
            password_hash=password_hash,
            failed_attempts=0,
            locked_until=None,
            updated_at=_now(),
        )
    )
    await session.commit()


async def record_login_success(session: AsyncSession, user_id: uuid.UUID) -> None:
    await session.execute(
        update(user_account)
        .where(user_account.c.user_id == user_id)
        .values(
            failed_attempts=0,
            locked_until=None,
            last_login_at=_now(),
            updated_at=_now(),
        )
    )
    await session.commit()


def lockout_seconds_for(failed_attempts: int) -> int:
    """Backoff progresivo acotado por ``login_lockout_seconds``."""
    settings = get_settings()
    base = max(1, settings.login_lockout_base_seconds)
    exponent = max(0, failed_attempts - 1)
    return min(settings.login_lockout_seconds, base * (2 ** exponent))


async def record_login_failure(
    session: AsyncSession, user_id: uuid.UUID, failed_attempts: int
) -> datetime | None:
    """Incrementa el contador y, si supera el umbral, bloquea temporalmente."""
    settings = get_settings()
    new_count = failed_attempts + 1
    locked_until: datetime | None = None
    if new_count >= settings.login_max_failures:
        locked_until = _now() + timedelta(seconds=lockout_seconds_for(new_count))
    await session.execute(
        update(user_account)
        .where(user_account.c.user_id == user_id)
        .values(
            failed_attempts=new_count,
            locked_until=locked_until,
            updated_at=_now(),
        )
    )
    await session.commit()
    return locked_until


def _field(row: Any, name: str) -> Any:
    mapping = getattr(row, "_mapping", None)
    if mapping is not None:
        return mapping[name]
    return getattr(row, name)


def is_locked(row: Any) -> bool:
    """``True`` si la cuenta está bloqueada temporalmente (``locked_until`` futuro)."""
    locked_until = _field(row, "locked_until")
    return locked_until is not None and locked_until > _now()


def is_active(row: Any) -> bool:
    return _field(row, "estado") == "activo" and _field(row, "disabled_at") is None


# =============================================================================
# Refresh tokens en PostgreSQL (rotativo con detección de reutilización)
# =============================================================================
def _record_from_row(row: Any) -> RefreshRecord:
    issued = row.issued_at
    return RefreshRecord(
        token_id=str(row.token_id),
        chain_id=str(row.chain_id),
        sub=str(row.sub),
        status=str(row.status),
        issued_at=int(issued.timestamp()) if issued is not None else 0,
        rotated_at=int(row.rotated_at.timestamp()) if row.rotated_at is not None else None,
    )


class DbRefreshStore:
    """Almacén de refresh respaldado por ``app.refresh_token``."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, token_id: str) -> RefreshRecord | None:
        result = await self._session.execute(
            select(refresh_token).where(refresh_token.c.token_id == token_id)
        )
        row = result.first()
        return _record_from_row(row) if row is not None else None

    async def put(self, record: RefreshRecord) -> None:
        issued_at = datetime.fromtimestamp(record.issued_at, tz=timezone.utc)
        rotated_at = (
            datetime.fromtimestamp(record.rotated_at, tz=timezone.utc)
            if record.rotated_at is not None
            else None
        )
        revoked_at = _now() if record.status == REVOKED else None
        stmt = pg_insert(refresh_token).values(
            token_id=record.token_id,
            chain_id=record.chain_id,
            sub=record.sub,
            status=record.status,
            issued_at=issued_at,
            rotated_at=rotated_at,
            revoked_at=revoked_at,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[refresh_token.c.token_id],
            set_={
                "chain_id": record.chain_id,
                "sub": record.sub,
                "status": record.status,
                "rotated_at": rotated_at,
                "revoked_at": revoked_at,
            },
        )
        await self._session.execute(stmt)
        await self._session.commit()

    async def revoke_chain(self, chain_id: str) -> None:
        await self._session.execute(
            update(refresh_token)
            .where(
                refresh_token.c.chain_id == chain_id,
                refresh_token.c.status != REVOKED,
            )
            .values(status=REVOKED, revoked_at=_now())
        )
        await self._session.commit()


__all__ = [
    "ACTIVE",
    "ROTATED",
    "REVOKED",
    "DbRefreshStore",
    "create_user",
    "disable_user",
    "get_user_by_id",
    "get_user_by_sub",
    "get_user_by_username",
    "is_active",
    "is_locked",
    "known_roles",
    "list_users",
    "record_login_failure",
    "record_login_success",
    "reset_password",
    "roles_for_sub",
    "roles_for_user",
    "set_roles",
    "update_user",
]
