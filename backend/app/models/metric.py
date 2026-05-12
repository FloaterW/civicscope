from sqlalchemy import Float, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Metric(Base):
    __tablename__ = "metrics"
    __table_args__ = (UniqueConstraint("geoid", "year", name="uq_metrics_geoid_year"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    geoid: Mapped[str] = mapped_column(
        ForeignKey("geographies.geoid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    median_income: Mapped[float | None] = mapped_column(Float, nullable=True)
    median_rent: Mapped[float | None] = mapped_column(Float, nullable=True)
    population: Mapped[int | None] = mapped_column(Integer, nullable=True)
    previous_population: Mapped[int | None] = mapped_column(Integer, nullable=True)
    renter_households: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rent_burden_pct: Mapped[float | None] = mapped_column(Float, nullable=True)
    affordability_index: Mapped[float | None] = mapped_column(Float, nullable=True)

    dwellings_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dwellings_single_detached: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dwellings_semi_detached: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dwellings_row_house: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dwellings_apt_duplex: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dwellings_apt_low_rise: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dwellings_apt_high_rise: Mapped[int | None] = mapped_column(Integer, nullable=True)
    owner_households: Mapped[int | None] = mapped_column(Integer, nullable=True)

    geography = relationship("Geography", back_populates="metrics")
