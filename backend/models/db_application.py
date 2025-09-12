from backend.db.base_class import Base
from typing import List, Optional
from sqlalchemy import ForeignKey, String, Date, TIMESTAMP, UUID, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from datetime import datetime, timezone
import uuid

class Application(Base):
    __tablename__ = "applications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))

    company_name: Mapped[str] = mapped_column(String(100), default="Company Name Not Found")
    position: Mapped[str] = mapped_column(String(100))
    application_date: Mapped[datetime] = mapped_column(Date, default=datetime.now(timezone.utc))
    status: Mapped[str] = mapped_column(String(20), default="applied")
    
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.now(timezone.utc), onupdate=datetime.now(timezone.utc))

    user: Mapped["User"] = relationship(back_populates="applications")
    
from backend.models.db_response import RecruiterResponse
from backend.models.db_event import Event

Application.responses = relationship("RecruiterResponse", back_populates="application", cascade="all, delete")
Application.events = relationship("Event", back_populates="application", cascade="all, delete")

