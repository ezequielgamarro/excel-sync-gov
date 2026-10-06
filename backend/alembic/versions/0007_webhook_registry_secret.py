"""webhook_registry + webhook_secret: registro de webhooks y versiones del secreto (T13)

Revision ID: 0007_webhook_registry_secret
Revises: 0006_audit_event
Create Date: 2026-10-03

T13 (Fase F1) — tablas ``app.webhook_registry`` y ``app.webhook_secret``: el
registro de los orígenes webhook (documento de Google Sheets asociado, estado y
revocación) y las versiones del secreto de firma (``key_id``, estado, fechas).
El **material del secreto** vive en el secret manager y en ``Script Properties``
del Apps Script; la BD guarda **solo metadata** (spec §9.2, RNF-02.e).

``app.webhook_registry`` (spec §7.9, §9.4, RF-01.e, RNF-03.f):

- ``webhook_id`` UUID PK (identidad estable del origen webhook).
- ``doc_id``: documento de Google Sheets declarado (un documento = un webhook).
- ``room_id``: sala a la que sirve el origen (una instancia = una sala;
  RNF-10.d, §7.9).
- ``estado`` ∈ {activo, revocado}: revocación **individual** sin afectar a toda
  la plataforma.
- ``revoked_at`` / ``last_seen_at``: revocación y latido para el panel de salud
  (RNF-07.e, RF-01.j).

``app.webhook_secret`` (spec §9.2–§9.3, RNF-02.e):

- ``key_id`` PK: versión del secreto referenciada por ``X-Webhook-Key-Id``.
- ``webhook_id``: FK **lógica** a ``app.webhook_registry.webhook_id`` (cada
  versión pertenece a un origen).
- ``estado`` ∈ {vigente, retirado}: alinea el ``key_id`` del mensaje con el
  secreto aceptado.
- ``not_before`` / ``not_after``: ventana de aceptación; la rotación mantiene un
  **solape de 24 h** en que el backend acepta la versión antigua y la nueva
  (§9.3).
- ``created_at`` / ``rotated_at``: trazabilidad de creación y rotación.
- **Solo metadata**: NO hay columna de secreto ni de hash de credencial. El
  material nunca entra a la BD (RNF-02.e, §9.5).

Idempotente: up con ``IF NOT EXISTS``; down con ``IF EXISTS``.
"""
from typing import Sequence, Union

from alembic import op

revision: str = "0007_webhook_registry_secret"
down_revision: Union[str, None] = "0006_audit_event"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_WEBHOOK_REGISTRY = (
    """CREATE TABLE IF NOT EXISTS app.webhook_registry (
    webhook_id   uuid        PRIMARY KEY DEFAULT app.uuidv7(),
    doc_id       text        NOT NULL,
    room_id      text        NOT NULL DEFAULT 'sala-central',
    estado       text        NOT NULL DEFAULT 'activo',
    revoked_at   timestamptz,
    last_seen_at timestamptz,
    created_at   timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT chk_webhook_registry_estado
        CHECK (estado IN ('activo', 'revocado'))
)""",
    "CREATE INDEX IF NOT EXISTS ix_webhook_registry_estado ON app.webhook_registry (estado)",
    "CREATE INDEX IF NOT EXISTS ix_webhook_registry_doc ON app.webhook_registry (doc_id)",
)

_WEBHOOK_SECRET = (
    """CREATE TABLE IF NOT EXISTS app.webhook_secret (
    key_id      text        PRIMARY KEY,
    webhook_id  uuid        NOT NULL,
    estado      text        NOT NULL DEFAULT 'vigente',
    not_before  timestamptz NOT NULL DEFAULT now(),
    not_after   timestamptz,
    created_at  timestamptz NOT NULL DEFAULT now(),
    rotated_at  timestamptz,
    CONSTRAINT chk_webhook_secret_estado
        CHECK (estado IN ('vigente', 'retirado')),
    CONSTRAINT chk_webhook_secret_ventana
        CHECK (not_after IS NULL OR not_after > not_before)
)""",
    "CREATE INDEX IF NOT EXISTS ix_webhook_secret_webhook ON app.webhook_secret (webhook_id)",
    "CREATE INDEX IF NOT EXISTS ix_webhook_secret_estado ON app.webhook_secret (estado)",
)

_COMMENTS = (
    "COMMENT ON TABLE app.webhook_registry IS "
    "'Registro de orígenes webhook (Google Sheets): documento asociado, estado y "
    "revocación individual (T13, §7.9, §9.4).'",
    "COMMENT ON COLUMN app.webhook_registry.doc_id IS "
    "'Documento de Google Sheets declarado de origen (un documento = un webhook).'",
    "COMMENT ON COLUMN app.webhook_registry.room_id IS "
    "'Sala servida por el origen; una instancia = una sala (RNF-10.d).'",
    "COMMENT ON COLUMN app.webhook_registry.estado IS "
    "'activo o revocado; la revocación es individual por origen.'",
    "COMMENT ON COLUMN app.webhook_registry.last_seen_at IS "
    "'Última recepción válida del webhook; alimenta el panel de salud (RNF-07.e).'",
    "COMMENT ON TABLE app.webhook_secret IS "
    "'Versiones del secreto de firma del webhook (solo metadata, T13, §9.2). "
    "El material vive en el secret manager y en Script Properties, nunca aquí "
    "(RNF-02.e).'",
    "COMMENT ON COLUMN app.webhook_secret.key_id IS "
    "'Versión del secreto referenciada por X-Webhook-Key-Id.'",
    "COMMENT ON COLUMN app.webhook_secret.webhook_id IS "
    "'FK lógica a app.webhook_registry.webhook_id (origen de la versión).'",
    "COMMENT ON COLUMN app.webhook_secret.estado IS "
    "'vigente o retirado; el backend solo acepta key_id vigentes.'",
    "COMMENT ON COLUMN app.webhook_secret.not_before IS "
    "'Inicio de la ventana de aceptación del key_id.'",
    "COMMENT ON COLUMN app.webhook_secret.not_after IS "
    "'Fin de la ventana de aceptación; la rotación mantiene 24 h de solape "
    "(§9.3).'",
)


def upgrade() -> None:
    for stmt in _WEBHOOK_REGISTRY:
        op.execute(stmt)
    for stmt in _WEBHOOK_SECRET:
        op.execute(stmt)
    for stmt in _COMMENTS:
        op.execute(stmt)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS app.webhook_secret")
    op.execute("DROP TABLE IF EXISTS app.webhook_registry")
