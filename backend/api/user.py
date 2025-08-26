from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.core.dependencies import get_current_user
from backend.db.session import get_db
from backend.models.db_users import User
from backend.service.user_service import register_user, login_user
from backend.models.schema import UserCreate, UserOut


router = APIRouter(prefix="/user", tags=["User"])

@router.post("/register", response_model=UserOut)
def register(user: UserCreate, db: Session = Depends(get_db)):
    return register_user(db, user.email, user.password)

@router.post("/login")
def login(user: UserCreate, db: Session = Depends(get_db)):
    token = login_user(db, user.email, user.password)
    return {"access_token": token, "token_type": "bearer"}

@router.get("/me", response_model=UserOut)
def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user