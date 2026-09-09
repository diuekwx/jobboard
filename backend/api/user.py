from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from sqlalchemy.orm import Session

from backend.core.auth import clear_auth_cookies
from backend.core.dependencies import get_current_user
from backend.db.session import get_db
from backend.models.db_integrationtokens import IntegrationToken
from backend.models.db_users import User
from backend.models.schema import UserOut
from backend.service.oauth_service import revoke_google_credentials
from backend.service.user_service import delete_user_account


router = APIRouter(prefix="/user", tags=["User"])


def _gmail_token(db: Session, user_id):
    return db.query(IntegrationToken).filter(
        IntegrationToken.user_id == user_id,
        IntegrationToken.provider == "gmail",
    ).first()


@router.get("/me", response_model=UserOut)
def read_users_me(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "gmail_connected": _gmail_token(db, current_user.id) is not None,
    }


@router.post("/logout", status_code=204)
def logout(
    request: Request,
    response: Response,
    _current_user: User = Depends(get_current_user),
):
    request.session.clear()
    clear_auth_cookies(response)


@router.post("/gmail/disconnect")
def disconnect_gmail(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    token = _gmail_token(db, current_user.id)
    if not token:
        return {"disconnected": True, "provider_revoked": False}

    revoked = revoke_google_credentials(token)
    db.delete(token)
    db.commit()
    return {"disconnected": True, "provider_revoked": revoked}


@router.delete("/me", status_code=204)
def delete_account(
    request: Request,
    response: Response,
    x_confirm_account_deletion: str | None = Header(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if x_confirm_account_deletion != "delete":
        raise HTTPException(status_code=400, detail="Account deletion confirmation is required")

    token = _gmail_token(db, current_user.id)
    if token:
        revoke_google_credentials(token)
    delete_user_account(db, current_user)
    request.session.clear()
    clear_auth_cookies(response)
