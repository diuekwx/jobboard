from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
import os
from dotenv import load_dotenv
from backend.models.schema import CredentialCreate
from backend.models.db_users import User
from backend.core.dependencies import get_current_user, get_db
from backend.service.oauth_service import save_credentials


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
SCOPES = ["https://www.googleapis.com/auth/gmail.readonly", "https://www.googleapis.com/auth/userinfo.email", "https://www.googleapis.com/auth/gmail.metadata"]

@router.get("/auth/google")
def auth_google():
    flow = Flow.from_client_config(
    client_config,
    scopes=SCOPES,
    redirect_uri=os.getenv("GOOGLE_REDIRECT_URI")
    )
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true"
    )
    return {"auth_url": auth_url}

@router.get("/auth/google/callback")
def auth_google_callback(request: Request, code: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    flow = Flow.from_client_config(
        client_config,
        scopes=SCOPES,
        redirect_uri=os.getenv("GOOGLE_REDIRECT_URI")
    )
    flow.fetch_token(code=code)

    credentials = flow.credentials

    sending = CredentialCreate(user_id = current_user.id,
                            access_token=credentials.token, 
                            refresh_token=credentials.refresh_token,
                            expires_at=credentials.expiry)
    
    save_credentials(db, sending)

    return {"message": "Gmail connected!"}