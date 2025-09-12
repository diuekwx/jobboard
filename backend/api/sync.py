from fastapi import Depends, APIRouter,Body
from sqlalchemy.orm import Session
from backend.models.db_users import User
from backend.core.dependencies import get_db, get_current_user
from backend.service.sync_service import sync
from datetime import datetime
from backend.models.schema import DateCreate

router = APIRouter(tags=["sync"])


@router.post("/sync_time")
def sync_applications(request: DateCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return sync(db, current_user.id, request.day)