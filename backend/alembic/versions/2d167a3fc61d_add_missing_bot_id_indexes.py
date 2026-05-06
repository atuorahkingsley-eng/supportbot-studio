"""add_missing_bot_id_indexes

Revision ID: 2d167a3fc61d
Revises: 8b37edf37050
Create Date: 2026-04-28 09:09:59.015142

Background
----------
The SQLAlchemy models all declare `bot_id = Column(..., index=True)`,
but the legacy `_migrate_columns()` helper in `database.py` added the
`bot_id` column to existing tables via raw `ALTER TABLE ... ADD COLUMN`
— which adds the column but does NOT create the declared index.

Result: every tenant-scoped query (`WHERE bot_id = ?`) on these tables
has been doing a full table scan. This migration creates the missing
indexes to match what the models always intended.

Additive only — no drops, no renames, no data movement.

Tables fixed (9):
  bot_config, conversations, faq_entries, leads, messages,
  report_schedules, sales_configs, visitor_conversations,
  webhook_configs

Verified empty (no pre-existing `ix_*_bot_id` indexes) on the dev DB
prior to writing — so each create_index will succeed cleanly.
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '2d167a3fc61d'
down_revision: Union[str, Sequence[str], None] = '8b37edf37050'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Single source of truth — used by both upgrade and downgrade so the
# pairing can never drift. Each entry: (index_name, table_name).
_INDEXES = [
    ('ix_bot_config_bot_id',            'bot_config'),
    ('ix_conversations_bot_id',         'conversations'),
    ('ix_faq_entries_bot_id',           'faq_entries'),
    ('ix_leads_bot_id',                 'leads'),
    ('ix_messages_bot_id',              'messages'),
    ('ix_report_schedules_bot_id',      'report_schedules'),
    ('ix_sales_configs_bot_id',         'sales_configs'),
    ('ix_visitor_conversations_bot_id', 'visitor_conversations'),
    ('ix_webhook_configs_bot_id',       'webhook_configs'),
]


def upgrade() -> None:
    """Create the missing bot_id indexes.

    if_not_exists=True: when migrating to a freshly-provisioned Postgres
    (e.g. Supabase), the baseline schema sometimes already carries these
    indexes — bare CREATE INDEX then fails with DuplicateTable. The IF
    NOT EXISTS guard makes the migration idempotent against either start
    state. Both Postgres and SQLite support the clause natively.
    """
    for index_name, table_name in _INDEXES:
        op.create_index(index_name, table_name, ['bot_id'], unique=False, if_not_exists=True)


def downgrade() -> None:
    """Drop the indexes added by upgrade(). Reverse order for symmetry."""
    for index_name, table_name in reversed(_INDEXES):
        op.drop_index(index_name, table_name=table_name)
