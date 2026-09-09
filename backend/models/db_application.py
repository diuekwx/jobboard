from backend.db.types import EncryptedText, UTCDateTime
from backend.db.base_class import Base
from typing import List, Optional
from sqlalchemy import ForeignKey, String, Date, TIMESTAMP, Uuid, Text, Boolean, UniqueConstraint, CheckConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import date, datetime, timezone
import uuid

class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (
        CheckConstraint(
            "status IN ('applied', 'process', 'assessment', 'interview', 'offer', "
            "'accepted', 'withdrawn', 'rejected')",
            name="ck_application_status",
        ),
        UniqueConstraint("user_id", "gmail_thread_lookup", name="uq_application_user_thread_lookup"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    company_name: Mapped[str] = mapped_column(EncryptedText("applications.company_name"), default="Company Name Not Found")
    position: Mapped[Optional[str]] = mapped_column(EncryptedText("applications.position"), nullable=True)
    application_date: Mapped[date] = mapped_column(Date, default=lambda: datetime.now(timezone.utc).date())
    status: Mapped[str] = mapped_column(String(20), default="applied")
    archived_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime(), nullable=True)

    # provenance / dedup
    source: Mapped[str] = mapped_column(String(20), default="manual")  # "manual" | "email"
    gmail_message_id: Mapped[Optional[str]] = mapped_column(EncryptedText("applications.gmail_message_id"), nullable=True)
    gmail_thread_id: Mapped[Optional[str]] = mapped_column(EncryptedText("applications.gmail_thread_id"), nullable=True)
    gmail_message_lookup: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    gmail_thread_lookup: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)

    notes: Mapped[Optional[str]] = mapped_column(EncryptedText("applications.notes"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user: Mapped["User"] = relationship(back_populates="applications")
    
from backend.models.db_response import RecruiterResponse
from backend.models.db_event import Event

Application.responses = relationship("RecruiterResponse", back_populates="application", cascade="all, delete")
Application.events = relationship("Event", back_populates="application", cascade="all, delete")

