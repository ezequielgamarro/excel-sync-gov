"""Auth nativa: usuarios locales + refresh tokens (T34/T35)

Revision ID: 0012_local_auth
Revises: 0011_f4_dashboard_support
Create Date: 2026-10-04

Fase F5 — autenticación **nativa** (sin Keycloak/SSO ni MFA). Se materializa el
almacén local de identidad en PostgreSQL:

- ``app.user_account``: usuario con hash **Argon2id**, estado activo/deshabilitado,
  ``created_at``/``last_login_at``, intentos fallidos y bloqueo temporal.
- ``app.user_role``: mapeo usuario→rol (contenedor de capacidades, §2.2.3); la
  capacidad efectiva se deriva vía ``app.role_capability`` (migración 0008).
- ``app.refresh_token``: refresh rotativo con **detección de reutilización**
  (cadena; reusar un token rotado revoca la cadena completa, RNF-03.b).

Privilegios mínimos: ``svc_dashboard`` recibe SELECT/INSERT/UPDATE en
``user_account`` y ``refresh_token``, y SELECT/INSERT/DELETE en ``user_role`` y
``role_capability`` (gestión de roles); sin DDL ni DELETE de usuarios (la baja es
lógica: ``estado='deshabilitado'``). Las contraseñas nunca se almacenan en claro
(la columna guarda el hash Argon2id).

Idempotente: ``CREATE TABLE/INDEX IF NOT EXISTS``; down con ``IF EXISTS``.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0012_local_auth"
down_revision: Union[str, None] = "0011_f4_dashboard_support"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_USER_ACCOUNT = (
    """CREATE TABLE IF NOT EXISTS app.user_account (
    user_id         uuid        PRIMARY KEY DEFAULT app.uuidv7(),
    sub             text        NOT NULL,
    username        text        NOT NULL,
    password_hash   text        NOT NULL,
    estado          text        NOT NULL DEFAULT 'activo',
    failed_attempts integer     NOT NULL DEFAULT 0,
    locked_until    timestamptz,
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz,
    last_login_at   timestamptz,
    disabled_at     timestamptz,
    CONSTRAINT uq_user_account_sub UNIQUE (sub),
    CONSTRAINT ck_user_account_estado CHECK (estado IN ('activo', 'deshabilitado'))
)""",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_user_account_username_lower ON app.user_account (lower(username))",
)

_USER_ROLE = """
CREATE TABLE IF NOT EXISTS app.user_role (
    user_id    uuid        NOT NULL REFERENCES app.user_account (user_id) ON DELETE CASCADE,
    role       text        NOT NULL,
    granted_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT pk_user_role PRIMARY KEY (user_id, role)
);
"""

_REFRESH_TOKEN = (
    """CREATE TABLE IF NOT EXISTS app.refresh_token (
    token_id   text        PRIMARY KEY,
    chain_id   text        NOT NULL,
    sub        text        NOT NULL,
    status     text        NOT NULL DEFAULT 'active',
    issued_at  timestamptz NOT NULL DEFAULT now(),
    rotated_at timestamptz,
    revoked_at timestamptz,
    CONSTRAINT ck_refresh_token_status CHECK (status IN ('active', 'rotated', 'revoked'))
)""",
    "CREATE INDEX IF NOT EXISTS ix_refresh_token_chain ON app.refresh_token (chain_id)",
    "CREATE INDEX IF NOT EXISTS ix_refresh_token_sub   ON app.refresh_token (sub)",
)

# Privilegios mínimos del rol de servicio para la gestión de identidad local.
_GRANTS = (
    "GRANT USAGE ON SCHEMA app TO svc_dashboard",
    "GRANT SELECT, INSERT, UPDATE ON app.user_account   TO svc_dashboard",
    "GRANT SELECT, INSERT, DELETE ON app.user_role       TO svc_dashboard",
    "GRANT SELECT, INSERT, UPDATE ON app.refresh_token   TO svc_dashboard",
    "GRANT SELECT, INSERT, DELETE ON app.role_capability TO svc_dashboard",
)

_COMMENTS = (
    "COMMENT ON TABLE app.user_account IS "
    "'Usuarios locales de auth nativa (T34): hash Argon2id, estado, bloqueo por "
    "intentos y trazabilidad de login. Sin IdP externo ni MFA.'",
    "COMMENT ON COLUMN app.user_account.sub IS "
    "'Identidad estable que viaja en el JWT (iss/aud/sub) y en la auditoría.'",
    "COMMENT ON COLUMN app.user_account.password_hash IS "
    "'Hash Argon2id (sal por usuario); NUNCA la contraseña en claro (RNF-13).'",
    "COMMENT ON TABLE app.user_role IS "
    "'Mapeo usuario→rol; la capacidad efectiva se deriva de app.role_capability.'",
    "COMMENT ON TABLE app.refresh_token IS "
    "'Refresh rotativo con detección de reutilización (cadena, RNF-03.b).'",
)


def upgrade() -> None:
    for stmt in _USER_ACCOUNT:
        op.execute(stmt)
    op.execute(_USER_ROLE)
    for stmt in _REFRESH_TOKEN:
        op.execute(stmt)
    for stmt in _GRANTS:
        op.execute(stmt)
    for stmt in _COMMENTS:
        op.execute(stmt)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS app.refresh_token")
    op.execute("DROP TABLE IF EXISTS app.user_role")
    op.execute("DROP TABLE IF EXISTS app.user_account")
