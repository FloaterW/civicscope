from sqlalchemy import ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class CmhcTractMetric(Base):
    """Real CMHC Starts & Completions Survey values published at the census-tract
    level (table codes 1.1.1.11 / 1.1.2.11), validated against CMHC's own
    published CMA totals during ETL.

    This is kept separate from ``cmhc_metrics`` (which is municipality-level and
    drives the inheritance/allocation fallback) so the two never mix: a tract is
    served its REAL value where one exists here, and the labeled allocation
    estimate everywhere else.
    """

    __tablename__ = "cmhc_tract_metrics"
    __table_args__ = (
        UniqueConstraint("geoid", "year", name="uq_cmhc_tract_metrics_geoid_year"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    geoid: Mapped[str] = mapped_column(
        ForeignKey("geographies.geoid", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    housing_starts_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    housing_completions: Mapped[int | None] = mapped_column(Integer, nullable=True)

    geography = relationship("Geography")
