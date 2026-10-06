"""platform_admin: otorga dash.view.live a platform-admin (decisión operativa)

Revision ID: 0013_platform_admin_view_live
Revises: 0012_local_auth
Create Date: 2026-10-04
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0013_platform_admin_view_live"
down_revision: Union[str, None] = "0012_local_auth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_GRANT = """
INSERT INTO app.role_capability (role, capability, granted) VALUES
    ('platform-admin', 'dash.view.live', true)
ON CONFLICT (role, capability) DO UPDATE SET granted = true;
"""

_REVOKE = """
DELETE FROM app.role_capability
 WHERE role = 'platform-admin' AND capability = 'dash.view.live';
"""


def upgrade() -> None:
    op.execute(_GRANT)


def downgrade() -> None:
    op.execute(_REVOKE)
