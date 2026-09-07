from backend.db.types import EncryptedText, UTCDateTime
from backend.db.base_class import Base
from typing import Optional
import uuid
from sqlalchemy import ForeignKey, String, DateTime, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, timezone

class IntegrationToken(Base):
    __tablename__ = "integration_tokens"
    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_token_user_provider"),)

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    provider: Mapped[str] = mapped_column(String(50))  # e.g., "gmail"

    external_user_id: Mapped[Optional[str]] = mapped_column(EncryptedText("integration_tokens.external_user_id"), nullable=True)

    access_token: Mapped[str] = mapped_column(EncryptedText("integration_tokens.access_token"))
    refresh_token: Mapped[str] = mapped_column(EncryptedText("integration_tokens.refresh_token"), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime())

    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )

    user: Mapped["User"] = relationship(back_populates="integration_tokens")
