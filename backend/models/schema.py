from pydantic import BaseModel, EmailStr
from uuid import UUID
from typing import Optional
from datetime import datetime

class UserCreate(BaseModel):
    email: EmailStr
    password: str

class UserOut(BaseModel):
    id: UUID
    email: EmailStr

    model_config = {"from_attributes": True}


class ApplicationCreate(BaseModel):
    company: str
    position: str
    status: str

class ApplicationOut(BaseModel):
    company_name: str
    position: str

    model_config = {"from_attributes": True}


# | None = None vs Optional  
class EditApplication(BaseModel):
    company: str
    position: str
    status: Optional[str] = None
    notes: Optional[str] = None


class EditApplicationOut(BaseModel):
    id: UUID
    user_id: UUID

    model_config = {"from_attributes": True}


class CredentialCreate(BaseModel):
    user_id: UUID
    access_token: str
    refresh_token: str
    expires_at: datetime

class GoogleCreate(BaseModel):
    email: str