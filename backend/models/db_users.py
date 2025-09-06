from backend.db.base_class import Base
from typing import List
from sqlalchemy import String, TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import Mapped
from sqlalchemy.orm import mapped_column
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from backend.models.db_application import Application
import uuid


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP, default=datetime.now(timezone.utc))
    

    applications: Mapped[List["Application"]] = relationship(back_populates="user", cascade="all, delete")
    integration_tokens: Mapped[List["IntegrationToken"]] = relationship(back_populates="user", cascade="all, delete")