from sqlalchemy.orm import Session

from backend.core.auth import create_access_token, recieve_jwt
from backend.models.db_users import User
from backend.models.schema import GoogleCreate


def create_new_google(db: Session, data: GoogleCreate):
    new_user = User(email=data.email)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


def login_google(email: str) -> str:
    return create_access_token(data={"sub": email})


def get_user_by_email(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()


def decode_jwt(token: str) -> str:
    return recieve_jwt(token)
