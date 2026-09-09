import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base_class import Base
from backend.db.types import EncryptedText, UTCDateTime


class ApplicationAction(Base):
    """Encrypted reversible user action and human-readable history entry."""

    __tablename__ = "application_actions"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    application_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(32), index=True)
    summary: Mapped[str] = mapped_column(EncryptedText("application_actions.summary"))
    undo_payload: Mapped[str | None] = mapped_column(EncryptedText("application_actions.undo_payload"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=lambda: datetime.now(timezone.utc))
    undone_at: Mapped[datetime | None] = mapped_column(UTCDateTime(), nullable=True)
