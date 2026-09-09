from fastapi import APIRouter, Depends, HTTPException, Request
from jose import JWTError

from backend.core.dependencies import get_current_user
from backend.models.db_users import User
from backend.models.schema import UserOut
from backend.service.user_service import decode_jwt


router = APIRouter(prefix="/user", tags=["User"])


@router.get("/me", response_model=UserOut)
def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.get("/ping")
def get_me(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        payload = decode_jwt(token)
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")

    return {"email": email}
