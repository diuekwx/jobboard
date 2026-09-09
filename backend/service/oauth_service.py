import os
import logging
from datetime import timezone

import requests
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from sqlalchemy.orm import Session

from backend.models.db_integrationtokens import IntegrationToken
from backend.models.schema import CredentialCreate

logger = logging.getLogger(__name__)


def save_credentials(db: Session, data: CredentialCreate):
    existing = db.query(IntegrationToken).filter_by(
        user_id=data.user_id,
        provider="gmail",
    ).first()

    if existing:
        existing.access_token = data.access_token
        existing.expires_at = data.expires_at
        if data.external_user_id:
            existing.external_user_id = data.external_user_id
        if data.refresh_token:
            existing.refresh_token = data.refresh_token
    else:
        credentials = IntegrationToken(
            user_id=data.user_id,
            provider="gmail",
            external_user_id=data.external_user_id,
            access_token=data.access_token,
            refresh_token=data.refresh_token,
            expires_at=data.expires_at,
        )
        db.add(credentials)
    db.commit()



def refresh_google_token(db: Session, integration_token: IntegrationToken) -> IntegrationToken:
    creds = Credentials(
        token=integration_token.access_token,
        refresh_token=integration_token.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        expiry=(
            integration_token.expires_at.astimezone(timezone.utc).replace(tzinfo=None)
            if integration_token.expires_at.tzinfo
            else integration_token.expires_at
        ),
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

        integration_token.access_token = creds.token
        integration_token.expires_at = creds.expiry
        if creds.refresh_token:
            integration_token.refresh_token = creds.refresh_token

        db.commit()
        db.refresh(integration_token)

    return integration_token


def revoke_google_credentials(integration_token: IntegrationToken) -> bool:
    """Best-effort provider revocation; callers must still remove local tokens."""
    token = integration_token.refresh_token or integration_token.access_token
    if not token:
        return False
    try:
        response = requests.post(
            "https://oauth2.googleapis.com/revoke",
            data={"token": token},
            headers={"content-type": "application/x-www-form-urlencoded"},
            timeout=5,
        )
        return response.status_code == 200
    except requests.RequestException:
        logger.warning("Google credential revocation request failed")
        return False
