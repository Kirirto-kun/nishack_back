"""add issue status events timeline

Revision ID: 9c6c9e3f2b7a
Revises: 5c9a1b2d3e4f
Create Date: 2026-03-19
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "9c6c9e3f2b7a"
down_revision: Union[str, Sequence[str], None] = "5c9a1b2d3e4f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use raw SQL to avoid SQLAlchemy enum-type DDL creation side effects.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS issue_status_events (
          id SERIAL PRIMARY KEY,
          issue_id INTEGER NOT NULL REFERENCES issues(id) ON DELETE CASCADE,
          from_status VARCHAR(50) NOT NULL,
          to_status VARCHAR(50) NOT NULL,
          changed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
          actor_role VARCHAR(50) NULL,
          actor_id INTEGER NULL
        );
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_issue_status_events_issue_id ON issue_status_events(issue_id);")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_issue_status_events_issue_id;")
    op.execute("DROP TABLE IF EXISTS issue_status_events;")

