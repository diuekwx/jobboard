from backend.db.base_class import Base
from typing import Optional
from sqlalchemy import ForeignKey, String, TIMESTAMP, UUID, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime, timezone
import uuid


class ProcessedMessage(Base):
    """Ledger of every Gmail message we've already looked at, so re-syncs are idempotent."""

    __tablename__ = "processed_messages"
    __table_args__ = (
        UniqueConstraint("user_id", "gmail_message_id", name="uq_processed_user_message"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    gmail_message_id: Mapped[str] = mapped_column(String(255), index=True)
    gmail_thread_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    application_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("applications.id", ondelete="SET NULL"), nullable=True
    )

    # created | needs_review | duplicate_thread | not_application
    # | rejected | rejection_duplicate | rejection_unmatched
    # | assessment | interview | stage_duplicate | advance_unmatched | error
    outcome: Mapped[str] = mapped_column(String(32))
    detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    processed_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.now(timezone.utc))
