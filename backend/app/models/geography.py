from sqlalchemy import JSON, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Geography(Base):
    __tablename__ = "geographies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    geoid: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    county: Mapped[str | None] = mapped_column(String(120), nullable=True, index=True)
    state: Mapped[str] = mapped_column(String(2), nullable=False, default="ON", index=True)
    geometry: Mapped[dict] = mapped_column(JSON, nullable=False)
    bbox: Mapped[list[float]] = mapped_column(JSON, nullable=False)
    geometry_source: Mapped[str] = mapped_column(
        String(240),
        nullable=False,
        default="Demo GeoJSON boundary; replace with official boundary ETL for production.",
    )

    metrics = relationship("Metric", back_populates="geography", cascade="all, delete-orphan")
