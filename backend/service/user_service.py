from sqlalchemy.orm import Session

from backend.core.auth import create_access_token
from backend.models.db_users import User
from backend.models.db_processedmessage import ProcessedMessage
from backend.models.db_scanjob import ScanJob
from backend.models.db_applicationaction import ApplicationAction
from backend.models.schema import GoogleCreate


def create_new_google(db: Session, data: GoogleCreate):
    new_user = User(email=data.email)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return new_user


def login_google(user: User, csrf_token: str) -> str:
    return create_access_token(data={"sub": str(user.id), "csrf": csrf_token})


def get_user_by_email(db: Session, email: str):
    return db.query(User).filter(User.email == email).first()


def delete_user_account(db: Session, user: User) -> None:
    """Delete account-owned data, including models without ORM relationships."""
    db.query(ProcessedMessage).filter(ProcessedMessage.user_id == user.id).delete(
        synchronize_session=False
    )
    db.query(ScanJob).filter(ScanJob.user_id == user.id).delete(
        synchronize_session=False
    )
    db.query(ApplicationAction).filter(ApplicationAction.user_id == user.id).delete(
        synchronize_session=False
    )
    db.delete(user)
    db.commit()
