from pydantic import BaseModel, EmailStr, Field, ConfigDict, model_validator
from uuid import UUID
from typing import Optional, Literal
from datetime import date, datetime

class UserOut(BaseModel):
    id: UUID
    email: EmailStr
    gmail_connected: bool = False

    model_config = {"from_attributes": True}


ApplicationStatus = Literal[
    "applied", "process", "assessment", "interview", "offer",
    "accepted", "withdrawn", "rejected",
]


class ApplicationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    company: str = Field(min_length=1, max_length=200)
    position: Optional[str] = Field(default=None, max_length=200)
    status: ApplicationStatus = "applied"
    time: Optional[datetime] = None
    notes: Optional[str] = Field(default=None, max_length=10000)


class ApplicationOut(BaseModel):
    id: UUID
    company_name: str
    position: Optional[str]
    status: ApplicationStatus
    model_config = {"from_attributes": True}


class EditApplication(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    company: Optional[str] = Field(default=None, min_length=1, max_length=200)
    position: Optional[str] = Field(default=None, min_length=1, max_length=200)
    status: Optional[ApplicationStatus] = None
    notes: Optional[str] = Field(default=None, max_length=10000)
    application_date: Optional[date] = None

    @model_validator(mode="after")
    def validate_patch(self):
        if not self.model_fields_set:
            raise ValueError("Provide at least one field")
        for field in ("company", "status"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"{field} cannot be null")
        return self


class EditApplicationOut(BaseModel):
    id: UUID
    user_id: UUID

    model_config = {"from_attributes": True}


class CredentialCreate(BaseModel):
    user_id: UUID
    external_user_id: Optional[str] = None
    access_token: str
    refresh_token: Optional[str] = None
    expires_at: datetime

class GoogleCreate(BaseModel):
    email: str

class DateCreate(BaseModel):
    day: datetime


class MergeApplication(BaseModel):
    target_id: UUID
