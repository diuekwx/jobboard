from fastapi import Depends, HTTPException, Request
from jose import JWTError
from sqlalchemy.orm import Session
from uuid import UUID
from backend.db.session import get_db
from backend.models.db_users import User
from backend.core.auth import decode_access_token

def get_current_user(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    try:
        user = db.get(User, UUID(user_id))
    except (TypeError, ValueError):
        raise HTTPException(status_code=401, detail="Invalid token") from None
    if user is None:
        raise HTTPException(status_code=401, detail="Invalid token")
    return user
