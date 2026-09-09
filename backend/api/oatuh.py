"""Google sign-in and Gmail authorization flow."""

from __future__ import annotations

import os
from time import time

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from sqlalchemy.orm import Session

from backend.core.auth import new_csrf_token, set_auth_cookies
from backend.core.dependencies import get_db
from backend.models.schema import CredentialCreate, GoogleCreate
from backend.service.oauth_service import save_credentials
from backend.service.user_service import create_new_google, get_user_by_email, login_google


router = APIRouter()


def _client_config() -> dict:
    return {
        "web": {
            "client_id": os.environ["GOOGLE_CLIENT_ID"],
            "client_secret": os.environ["GOOGLE_CLIENT_SECRET"],
            "auth_uri": os.getenv("GOOGLE_AUTH_URI", "https://accounts.google.com/o/oauth2/auth"),
            "token_uri": os.getenv("GOOGLE_TOKEN_URI", "https://oauth2.googleapis.com/token"),
            "redirect_uris": [os.environ["GOOGLE_REDIRECT_URI"]],
        }
    }


def _flow() -> Flow:
    scopes = os.getenv(
        "SCOPES",
        "openid https://www.googleapis.com/auth/userinfo.email "
        "https://www.googleapis.com/auth/gmail.readonly",
    ).split()
    return Flow.from_client_config(
        _client_config(), scopes=scopes, redirect_uri=os.environ["GOOGLE_REDIRECT_URI"]
    )


@router.get("/auth/google")
def auth_google(request: Request):
    flow = _flow()
    auth_url, state = flow.authorization_url(
        access_type="offline",
        include_granted_scopes="true",
        prompt="consent",
    )
    request.session.clear()
    request.session.update({"google_oauth_state": state, "issued_at": int(time())})
    return {"auth_url": auth_url}


@router.get("/auth/google/callback")
def auth_google_callback(
    request: Request,
    code: str,
    state: str,
    db: Session = Depends(get_db),
):
    stored_state = request.session.pop("google_oauth_state", None)
    issued_at = request.session.pop("issued_at", 0)
    if not stored_state or stored_state != state or int(time()) - int(issued_at) > 600:
        request.session.clear()
        raise HTTPException(status_code=400, detail="OAuth session is invalid or expired")

    flow = _flow()
    try:
        flow.fetch_token(code=code)
        credentials = flow.credentials
        user_info = (
            build("oauth2", "v2", credentials=credentials, cache_discovery=False)
            .userinfo().get().execute()
        )
    except Exception:
        # Provider errors may contain authorization codes or response bodies.
        raise HTTPException(status_code=400, detail="Google authorization failed") from None

    user_email = user_info.get("email")
    if not user_email or user_info.get("verified_email") is not True:
        raise HTTPException(status_code=400, detail="A verified Google email is required")

    db_user = get_user_by_email(db, user_email)
    if not db_user:
        db_user = create_new_google(db, GoogleCreate(email=user_email))

    save_credentials(
        db,
        CredentialCreate(
            user_id=db_user.id,
            external_user_id=user_info.get("id"),
            access_token=credentials.token,
            refresh_token=credentials.refresh_token,
            expires_at=credentials.expiry,
        ),
    )

    csrf_token = new_csrf_token()
    token = login_google(db_user, csrf_token)
    response = RedirectResponse(url=os.environ["FRONTEND_REDIRECT"], status_code=303)
    set_auth_cookies(response, token, csrf_token)
    request.session.clear()
    return response
