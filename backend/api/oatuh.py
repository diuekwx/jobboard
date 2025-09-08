from fastapi import APIRouter, Request, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
import os
from dotenv import load_dotenv
from backend.models.schema import CredentialCreate, GoogleCreate
from backend.core.dependencies import get_db
from backend.service.oauth_service import save_credentials
from backend.service.user_service import get_user_by_email, create_new_google, login_goolge
from googleapiclient.discovery import build 
from backend.core.auth import create_access_token
import uuid
from fastapi.responses import RedirectResponse


load_dotenv()

client_config = {
    "web": {
        "client_id": os.getenv("GOOGLE_CLIENT_ID"),
        "project_id": "my-project",  # optional
        "auth_uri": os.getenv("GOOGLE_AUTH_URI"),
        "token_uri": os.getenv("GOOGLE_TOKEN_URI"),
        "client_secret": os.getenv("GOOGLE_CLIENT_SECRET"),
        "redirect_uris": [os.getenv("GOOGLE_REDIRECT_URI")]
    }
}
router = APIRouter()

_state_store = {}

@router.get("/auth/google")
def auth_google(request: Request):
    scopes = os.getenv("SCOPES").split()

    state_id = str(uuid.uuid4())
    state_param = "some_random_state"

    _state_store[state_id] = state_param


    flow = Flow.from_client_config(
    client_config,
    scopes=scopes,
    redirect_uri=os.getenv("GOOGLE_REDIRECT_URI")
    )
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        # prompt="consent"
    )
    # ?? 
    request.session["google_oauth_state"] = state
    print(f"state: {state}")
    print("Session before return:", request.session)
    print("Session contents:", request.session)
    stored_state = request.session.get("google_oauth_state")
    print(f"stored state: {stored_state}")

    return {"auth_url": auth_url}

@router.get("/auth/google/callback")
# def auth_google_callback(request: Request, code: str, state: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
def auth_google_callback(request: Request, code: str, state: str, db: Session = Depends(get_db)):
    # stored_state = request.session.pop("google_oauth_state", None)

    stored_state = request.session.get("google_oauth_state")

    if not stored_state or stored_state != state:
        raise HTTPException(status_code=400, detail="State parameter mismatch.")
    
    scopes = os.getenv("SCOPES").split()

    flow = Flow.from_client_config(
        client_config,
        scopes=scopes,
        redirect_uri=os.getenv("GOOGLE_REDIRECT_URI")
    )
    flow.fetch_token(code=code)

    credentials = flow.credentials


    service = build('oauth2', 'v2', credentials=credentials)
    user_info = service.userinfo().get().execute()

    user_email = user_info.get("email")

    if not user_email:
        raise HTTPException(status_code=400, detail="cant retrieve email")

    db_user = get_user_by_email(db, user_email)

    if not db_user:
        new_user_data = GoogleCreate(email=user_email)
        db_user = create_new_google(db, new_user_data)

    if not db_user:
        raise HTTPException(status_code=400, detail="User creation failed")

    # app_access_token = create_access_token(data={"sub": db_user.email})

    sending = CredentialCreate(
                        user_id = db_user.id,
                        access_token=credentials.token, 
                        refresh_token=credentials.refresh_token,
                        expires_at=credentials.expiry)


    save_credentials(db, sending)
    frontend_redirect = os.getenv("FRONTEND_REDIRECT")

    jwt = login_goolge(user_email)
    response = RedirectResponse(url=frontend_redirect)
    response.set_cookie(
        key="access_token",
        value=jwt,
        httponly=True,
        secure=False,
        samesite="lax")

    # return {"access_token":app_access_token, "token_type":"bearer", "message": "Gmail connected!"}
    return response
