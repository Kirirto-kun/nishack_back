"""add postgis, geom columns, and pois

Revision ID: 5c9a1b2d3e4f
Revises: 1b6c33ff827b
Create Date: 2026-03-19

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5c9a1b2d3e4f"
down_revision: Union[str, Sequence[str], None] = "1b6c33ff827b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Ensure PostGIS is available for Geometry columns / functions.
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS postgis"))

    # issues: category + geom (SRID 4326)
    op.add_column("issues", sa.Column("category", sa.String(length=100), nullable=True))
    op.add_column(
        "issues",
        sa.Column(
            "geom",
            sa.Text(),  # real type set via ALTER below
            nullable=True,
        ),
    )
    op.execute(
        sa.text(
            "ALTER TABLE issues "
            "ALTER COLUMN geom "
            "TYPE geometry(POINT, 4326) "
            "USING (ST_SetSRID(ST_MakePoint(longitude, latitude), 4326))"
        )
    )
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_issues_geom ON issues USING GIST (geom)"))

    # pois table
    op.create_table(
        "pois",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("osm_id", sa.BigInteger(), nullable=False, unique=True, index=True),
        sa.Column("name", sa.String(length=500), nullable=True),
        sa.Column("category", sa.String(length=100), nullable=False, index=True),
        sa.Column("lat", sa.Float(), nullable=False),
        sa.Column("lon", sa.Float(), nullable=False),
        sa.Column("geom", sa.Text(), nullable=False),
    )
    op.execute(
        sa.text(
            "ALTER TABLE pois "
            "ALTER COLUMN geom "
            "TYPE geometry(POINT, 4326) "
            "USING (ST_SetSRID(ST_MakePoint(lon, lat), 4326))"
        )
    )
    op.execute(sa.text("CREATE INDEX IF NOT EXISTS ix_pois_geom ON pois USING GIST (geom)"))


def downgrade() -> None:
    op.drop_index("ix_pois_geom", table_name="pois")
    op.drop_table("pois")

    op.drop_index("ix_issues_geom", table_name="issues")
    op.drop_column("issues", "geom")
    op.drop_column("issues", "category")
    # Keep extension; other objects may rely on it.

