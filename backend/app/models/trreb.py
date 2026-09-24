"""Immutable TRREB release data, separate from Census and CMHC metrics."""
from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


def now():
    return datetime.now(timezone.utc)


class TrrebRelease(Base):
    __tablename__ = 'trreb_releases'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    archive_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    manifest: Mapped[dict] = mapped_column(JSON, nullable=False)
    audit_summary: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)


class TrrebObservation(Base):
    __tablename__ = 'trreb_observations'
    release_id: Mapped[str] = mapped_column(ForeignKey('trreb_releases.id'), primary_key=True)
    geoid: Mapped[str] = mapped_column(String(7), primary_key=True)
    period: Mapped[str] = mapped_column(String(7), primary_key=True)
    payload: Mapped[dict] = mapped_column(JSON, nullable=False)


class TrrebPublication(Base):
    __tablename__ = 'trreb_publication'
    __table_args__ = (CheckConstraint('id = 1', name='trreb_publication_singleton'),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    release_id: Mapped[str | None] = mapped_column(ForeignKey('trreb_releases.id'), nullable=True)


class TrrebPublicationEvent(Base):
    __tablename__ = 'trreb_publication_events'
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    release_id: Mapped[str | None] = mapped_column(ForeignKey('trreb_releases.id'), nullable=True)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, nullable=False)
