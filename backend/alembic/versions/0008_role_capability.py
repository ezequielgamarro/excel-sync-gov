"""role_capability: mapeo rol→capacidad + seeds (T14)

Revision ID: 0008_role_capability
Revises: 0007_webhook_registry_secret
Create Date: 2026-10-03

T14 (Fase F1) — tabla ``app.role_capability``: mapeo **configurable** de rol →
capacidad, desacoplado de cualquier IdP externo (las capacidades son el único
objeto que el backend comprueba; §2.2.3, RNF-03.c). Añadir un rol nuevo no obliga
a tocar el código de autorización. El mapeo aplica a la auth nativa JWT.

Semántica del mapeo:

- ``granted = true`` autoriza la capacidad; **ausencia de fila** (o
  ``granted = false``) se interpreta como denegación (fail-closed).
- Seeds: solo las celdas «Sí» de la matriz §2.2.3 (las celdas «No» se dejan
  implícitas, no se siembran). Concretamente:
    · viewer:        dash.view.live
    · supervisor:    dash.view.live, dash.view.history, dash.export.csv,
                     platform.replay
    · auditor:       dash.view.history, dash.export.csv, audit.view,
                     platform.replay
    · platform-admin: dash.view.live, platform.manage_webhook,
                      platform.manage_users, platform.rotate_secrets
- Decisión operativa (posterior a §2.2.3): ``platform-admin`` **sí** incluye
  ``dash.view.live``, además de sus capacidades de administración, para que el
  administrador pueda ver el dashboard en vivo. La migración ``0013`` aplica
  este permiso a las bases de datos ya migradas.
- El ``DELETE`` previo de los cuatro roles sembrados elimina filas obsoletas de
  versiones anteriores del seed y mantiene el upgrade idempotente.

Idempotente: ``ON CONFLICT (role, capability) DO NOTHING``; down con
``IF EXISTS``.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0008_role_capability"
down_revision: Union[str, None] = "0007_webhook_registry_secret"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ROLE_CAPABILITY = """
CREATE TABLE IF NOT EXISTS app.role_capability (
    role       text    NOT NULL,
    capability text    NOT NULL,
    granted    boolean NOT NULL DEFAULT true,
    CONSTRAINT pk_role_capability PRIMARY KEY (role, capability)
);
"""

# Seeds = celdas «Sí» de la matriz §2.2.3 (las «No» quedan implícitas).
# El DELETE previo acota el borrado a los roles sembrados y limpia seeds
# obsoletos; el INSERT ... ON CONFLICT DO NOTHING lo hace re-ejecutable.
_ROLE_CAPABILITY_SEED_ROLES = "'viewer', 'supervisor', 'auditor', 'platform-admin'"

_CLEAR_SEEDS = f"""
DELETE FROM app.role_capability
 WHERE role IN ({_ROLE_CAPABILITY_SEED_ROLES});
"""

_SEEDS = """
INSERT INTO app.role_capability (role, capability, granted) VALUES
    ('viewer',         'dash.view.live',          true),
    ('supervisor',     'dash.view.live',          true),
    ('supervisor',     'dash.view.history',       true),
    ('supervisor',     'dash.export.csv',         true),
    ('supervisor',     'platform.replay',         true),
    ('auditor',        'dash.view.history',       true),
    ('auditor',        'dash.export.csv',         true),
    ('auditor',        'audit.view',              true),
    ('auditor',        'platform.replay',         true),
    ('platform-admin', 'dash.view.live',          true),
    ('platform-admin', 'platform.manage_webhook', true),
    ('platform-admin', 'platform.manage_users',   true),
    ('platform-admin', 'platform.rotate_secrets', true)
ON CONFLICT (role, capability) DO NOTHING;
"""

_COMMENTS = (
    "COMMENT ON TABLE app.role_capability IS "
    "'Mapeo configurable rol→capacidad (T14, §2.2.3), desacoplado de IdP externo "
    "(auth nativa JWT). "
    "Ausencia de fila = denegación (fail-closed).'",
    "COMMENT ON COLUMN app.role_capability.granted IS "
    "'true autoriza la capacidad; false o fila ausente = denegación.'",
)


def upgrade() -> None:
    op.execute(_ROLE_CAPABILITY)
    op.execute(_CLEAR_SEEDS)
    op.execute(_SEEDS)
    for stmt in _COMMENTS:
        op.execute(stmt)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS app.role_capability")
