from sqlalchemy import Float, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CmhcMetric(Base):
    __tablename__ = "cmhc_metrics"
    __table_args__ = (UniqueConstraint("geoid", "year", name="uq_cmhc_metrics_geoid_year"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    geoid: Mapped[str] = mapped_column(
        ForeignKey("geographies.geoid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # Rental Market Survey
    vacancy_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    average_rent_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    average_rent_bachelor: Mapped[float | None] = mapped_column(Float, nullable=True)
    average_rent_1br: Mapped[float | None] = mapped_column(Float, nullable=True)
    average_rent_2br: Mapped[float | None] = mapped_column(Float, nullable=True)
    average_rent_3br_plus: Mapped[float | None] = mapped_column(Float, nullable=True)
    turnover_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    availability_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    rental_universe: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Starts & Completions
    housing_starts_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    housing_starts_single: Mapped[int | None] = mapped_column(Integer, nullable=True)
    housing_starts_semi: Mapped[int | None] = mapped_column(Integer, nullable=True)
    housing_starts_row: Mapped[int | None] = mapped_column(Integer, nullable=True)
    housing_starts_apartment: Mapped[int | None] = mapped_column(Integer, nullable=True)
    housing_completions: Mapped[int | None] = mapped_column(Integer, nullable=True)
    units_under_construction: Mapped[int | None] = mapped_column(Integer, nullable=True)

    geography = relationship("Geography", back_populates="cmhc_metrics")
