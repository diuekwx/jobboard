from backend.db.types import EncryptedText, UTCDateTime
from backend.db.base_class import Base
from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, timezone
import uuid

class RecruiterResponse(Base):
    __tablename__ = "recruiter_responses"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    sender_email: Mapped[str] = mapped_column(EncryptedText("recruiter_responses.sender_email"))
    subject: Mapped[str] = mapped_column(EncryptedText("recruiter_responses.subject"))
    received_at: Mapped[datetime] = mapped_column(UTCDateTime(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=lambda: datetime.now(timezone.utc))

    application: Mapped["Application"] = relationship(back_populates="responses")
