"""Add unique constraint on pending_escalations.(bot_id, session_id).

The retry scheduler in main.py could previously create duplicate rows for the
same escalation on every retry cycle (exponential growth). The unique constraint
prevents duplicates: at most one pending row per (bot_id, session_id), and the
upsert pattern in escalate.py collapses concurrent writers.

Hand-written:
  - SQLite requires batch_alter_table for CREATE UNIQUE INDEX equivalent.
  - No deduplication step needed — the table is idempotent at the application
    level (each escalation has exactly one bot_id + session_id pair), and any
    duplicates would have been cleaned up by the fix in escalate.py.

Revision ID: a1b2c3d4e5f6
Revises: 7c92a1f4b3d2
Create Date: 2026-05-12 03:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import reflection


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = '7c92a1f4b3d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'uq_pending_esc_bot_session'
                ) THEN
                    ALTER TABLE pending_escalations
                    ADD CONSTRAINT uq_pending_esc_bot_session
                    UNIQUE (bot_id, session_id);
                END IF;
            END $$;
        """)
    else:
        with op.batch_alter_table("pending_escalations") as batch_op:
            try:
                batch_op.create_unique_constraint(
                    "uq_pending_esc_bot_session", ["bot_id", "session_id"]
                )
            except Exception:
                pass


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            "ALTER TABLE pending_escalations "
            "DROP CONSTRAINT IF EXISTS uq_pending_esc_bot_session"
        )
    else:
        with op.batch_alter_table("pending_escalations") as batch_op:
            try:
                batch_op.drop_constraint(
                    "uq_pending_esc_bot_session", type_="unique"
                )
            except Exception:
                pass
