from pydantic import BaseModel, EmailStr
from uuid import UUID
from typing import Optional

class UserCreate(BaseModel):
    email: EmailStr
    password: str

class UserOut(BaseModel):
    id: UUID
    email: EmailStr

    class Config:
        orm_mode = True

class ApplicationCreate(BaseModel):
    company: str
    position: str
    status: str

class ApplicationOut(BaseModel):
    company: str
    position: str

    class Config:
        orm_mode: True

# | None = None vs Optional  
class EditApplication(BaseModel):
    company: str
    position: str
    status: Optional[str] = None
    notes: Optional[str] = None


class EditApplicationOut(BaseModel):
    id: UUID
    user_id: UUID

    class config: 
        orm_model = True