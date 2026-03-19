from __future__ import annotations

from geoalchemy2 import Geometry
from sqlalchemy import BigInteger, Float, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Poi(Base):
    __tablename__ = "pois"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    osm_id: Mapped[int] = mapped_column(BigInteger, nullable=False, unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    geom: Mapped[object] = mapped_column(Geometry(geometry_type="POINT", srid=4326), nullable=False)

