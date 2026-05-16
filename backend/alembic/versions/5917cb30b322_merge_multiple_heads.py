"""merge_multiple_heads

Revision ID: 5917cb30b322
Revises: a0b1c2d3e4f5, b2c4e6f8a1d3
Create Date: 2026-05-16 10:15:14.389651

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5917cb30b322'
down_revision: Union[str, Sequence[str], None] = ('a0b1c2d3e4f5', 'b2c4e6f8a1d3')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
