"""Add expires_at column to revoked_tokens.

The column enables a cleanup job (main.py) to purge expired entries
from the denylist instead of accumulating forever.

Revision ID: a0b1c2d3e4f5
Revises: f7e8d9c0b1a2
Create Date: 2026-05-16 06:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a0b1c2d3e4f5"
down_revision: Union[str, Sequence[str], None] = "f7e8d9c0b1a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("revoked_tokens", sa.Column("expires_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("revoked_tokens", "expires_at")
