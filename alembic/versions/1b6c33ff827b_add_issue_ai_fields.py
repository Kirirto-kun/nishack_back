"""add issue ai fields

Revision ID: 1b6c33ff827b
Revises: b2c3d4e5f6a7
Create Date: 2026-03-19 12:25:50.429926

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1b6c33ff827b'
down_revision: Union[str, Sequence[str], None] = '801bc0b6d2d6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('issues', sa.Column('ai_admin_summary', sa.Text(), nullable=True))
    op.add_column('issues', sa.Column('ai_analyzed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('issues', sa.Column('ai_error', sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('issues', 'ai_error')
    op.drop_column('issues', 'ai_analyzed_at')
    op.drop_column('issues', 'ai_admin_summary')
