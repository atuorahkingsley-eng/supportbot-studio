"""Add unique constraint on usage_logs.(bot_id, date).

Concurrent runs of `_log_daily_usage` (e.g. APScheduler instance overlap on
startup, or retry-after-failure) previously created duplicate rows for the
same (tenant, day) tuple, which corrupted billing roll-ups. The unique
constraint plus the dialect-aware upsert in main.py keep the table
canonical: at most one row per (bot_id, date), and concurrent writers
collapse into a single UPDATE.

Hand-written:
  - Deduplicates any pre-existing duplicate rows so the constraint can
    be added without an IntegrityError. The "winner" is the row with the
    largest total_messages (most-complete snapshot), with ties broken
    by max(id).
  - Issues the constraint via batch_alter_table for SQLite compatibility.

Revision ID: 7c92a1f4b3d2
Revises: d5465a04bb14
Create Date: 2026-05-12 02:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine import reflection


revision: str = '7c92a1f4b3d2'
down_revision: Union[str, Sequence[str], None] = 'd5465a04bb14'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Deduplicate first ─────────────────────────────────────────────────────
    # Without this the ALTER TABLE will fail on any tenant that previously hit
    # the race. Strategy: for each (bot_id, date) group, keep the row with the
    # highest total_messages, deleting the rest. Ties broken by max(id) so the
    # result is deterministic. Works on both SQLite and Postgres — uses a
    # correlated subquery, no dialect-specific window functions.
    conn = op.get_bind()
    conn.execute(sa.text("""
        DELETE FROM usage_logs
        WHERE id NOT IN (
            SELECT MAX(u1.id)
            FROM usage_logs u1
            WHERE u1.total_messages = (
                SELECT MAX(u2.total_messages)
                FROM usage_logs u2
                WHERE u2.bot_id = u1.bot_id
                  AND u2.date = u1.date
            )
            GROUP BY u1.bot_id, u1.date
        )
    """))

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'uq_usagelog_bot_date'
                ) THEN
                    ALTER TABLE usage_logs
                    ADD CONSTRAINT uq_usagelog_bot_date
                    UNIQUE (bot_id, date);
                END IF;
            END $$;
        """)
    else:
        with op.batch_alter_table("usage_logs") as batch_op:
            try:
                batch_op.create_unique_constraint(
                    "uq_usagelog_bot_date", ["bot_id", "date"]
                )
            except Exception:
                pass


def downgrade() -> None:
    with op.batch_alter_table("usage_logs") as batch_op:
        batch_op.drop_constraint("uq_usagelog_bot_date", type_="unique")
