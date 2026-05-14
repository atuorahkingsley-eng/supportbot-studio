"""Create usage_alerts table for tracking sent overage warnings.

The overage warning system (backend/services/usage_alerts.py) uses this table
to ensure each threshold warning (80%, 95%, limit_reached) is sent at most
once per tenant per month. The unique constraint on (bot_id, month, threshold)
prevents duplicate alerts from concurrent background tasks.

Revision ID: f7e8d9c0b1a2
Revises: a1b2c3d4e5f6
Create Date: 2026-05-14 03:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f7e8d9c0b1a2"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "usage_alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("bot_id", sa.String(), nullable=False),
        sa.Column("month", sa.String(), nullable=False),
        sa.Column("threshold", sa.String(), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(
            ["bot_id"],
            ["tenants.bot_id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "bot_id", "month", "threshold",
            name="uq_usage_alert_bot_month_threshold",
        ),
    )
    op.create_index(
        op.f("ix_usage_alerts_bot_id"),
        "usage_alerts", ["bot_id"],
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_usage_alerts_bot_id"),
        table_name="usage_alerts",
    )
    op.drop_table("usage_alerts")
