from fastapi import APIRouter, Depends, Request, Response, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from backend.core.dependencies import get_current_user
from backend.db.session import get_db
from backend.models.db_users import User
from backend.service.user_service import register_user, login_user, decode_jwt
from backend.models.schema import UserCreate, UserOut
from fastapi.security import OAuth2PasswordRequestForm
from jose import jwt, JWTError


router = APIRouter(prefix="/user", tags=["User"])

@router.post("/register", response_model=UserOut)
def register(user: UserCreate, db: Session = Depends(get_db)):
    return register_user(db, user.email, user.password)

# respense -> auto http response fastapi will be sending  
@router.post("/login")
def login(user: UserCreate, db: Session = Depends(get_db)):
    token = login_user(db, user.email, user.password)
    response = JSONResponse(content={"message": "Login Success"})

    response.set_cookie(
        key="access_token",
        value = token,
        httponly=True,
        secure=False, #true 
        samesite="lax" #None
    )
    return response

# @router.post("/login")
# def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
#     token = login_user(db, form_data.username, form_data.password)
#     return {"access_token": token, "token_type": "bearer"}

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