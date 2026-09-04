from backend.db.base_class import Base
from typing import Optional
from sqlalchemy import ForeignKey, String, TIMESTAMP, UUID, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, timezone
import uuid


class Event(Base):
    """A dated thing an application is waiting on: an interview slot or an
    assessment deadline.

    ``end_time`` is nullable because most recruiting mail names a start and
    nothing else, and a deadline has no end at all. ``source_message_id`` is
    the Gmail message the event was read out of, so re-syncing the same mail
    updates the row instead of stacking duplicates.
    """

    __tablename__ = "events"
    __table_args__ = (
        Index("ix_events_application_start", "application_id", "start_time"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"))
    event_type: Mapped[str] = mapped_column(String(50))  # "interview" | "assessment"
    title: Mapped[str] = mapped_column(String(100))
    start_time: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False)
    end_time: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP, nullable=True)
    source_message_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True, index=True)
    google_event_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.now(timezone.utc))

    application: Mapped["Application"] = relationship(back_populates="events")
