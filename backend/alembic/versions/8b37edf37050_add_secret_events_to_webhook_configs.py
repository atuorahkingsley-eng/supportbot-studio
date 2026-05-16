"""add_secret_events_to_webhook_configs

Revision ID: 8b37edf37050
Revises: 71c8f4dcc450
Create Date: 2026-04-28 08:54:06.726378

Additive-only migration.

Adds two nullable columns to webhook_configs to support generic
HTTPS webhooks with HMAC signing + per-event subscriptions:

  - secret  TEXT NULL  — HMAC signing key (used when platform == 'custom_https')
  - events  TEXT NULL  — JSON-encoded list of subscribed event types

Existing rows are unaffected (both NULL by default).

Note: autogenerate also surfaced unrelated drift (TEXT/String type
churn, missing bot_id indexes left behind by the legacy
_migrate_columns() helper, and an orphan visitors_backup table). All
of that has been intentionally stripped from this revision — it is
out of scope for the webhook change and will be addressed in a
separate, dedicated cleanup migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import reflection


# revision identifiers, used by Alembic.
revision: str = '8b37edf37050'
down_revision: Union[str, Sequence[str], None] = '71c8f4dcc450'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add HMAC secret + JSON events list to webhook_configs if not already present."""
    bind = op.get_bind()
    inspector = reflection.Inspector.from_engine(bind)
    cols = {c['name'] for c in inspector.get_columns('webhook_configs')}

    if 'secret' not in cols:
        op.add_column('webhook_configs', sa.Column('secret', sa.String(), nullable=True))
    if 'events' not in cols:
        op.add_column('webhook_configs', sa.Column('events', sa.Text(), nullable=True))


def downgrade() -> None:
    """Reverse the additive change."""
    bind = op.get_bind()
    inspector = reflection.Inspector.from_engine(bind)
    cols = {c['name'] for c in inspector.get_columns('webhook_configs')}

    if 'events' in cols:
        op.drop_column('webhook_configs', 'events')
    if 'secret' in cols:
        op.drop_column('webhook_configs', 'secret')
