from ..db.base_class import Base
from typing import Optional
from sqlalchemy import ForeignKey, String, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from db_application import Application
from datetime import datetime
import uuid


class Event(Base):
    __tablename__ = "events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"))
    event_type: Mapped[str] = mapped_column(String(50))  
    title: Mapped[str] = mapped_column(String(100))
    start_time: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False)
    end_time: Mapped[datetime] = mapped_column(TIMESTAMP, nullable=False)
    google_event_id: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.utcnow)

    application: Mapped["Application"] = relationship(back_populates="events")