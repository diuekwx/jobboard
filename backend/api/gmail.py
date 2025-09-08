from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from backend.core.dependencies import get_db, get_current_user
from backend.models.db_integrationtokens import IntegrationToken
from backend.models.db_users import User
from backend.service.oauth_service import refresh_google_token
import os
from backend.service.gmail_service import extract_company, extract_company_spacy
router = APIRouter(tags=["gmail"])

@router.get("/fetch-applications")
def fetch_job_applications(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):

    integration_token = db.query(IntegrationToken).filter(
        IntegrationToken.user_id == current_user.id,
        IntegrationToken.provider == "gmail"
    ).first()

    if not integration_token:
        return {"error": "gmail not connected"}
    
    integration_token = refresh_google_token(db, integration_token)

    creds = Credentials(
        token=integration_token.access_token,
        refresh_token=integration_token.refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        scopes=os.getenv("SCOPES")
    )
    
    service = build("gmail", "v1", credentials=creds)
    query = 'in:inbox subject:("thank you for applying" OR "application received" OR "application submitted")'

    results = service.users().messages().list(userId="me", q=query).execute()
    messages = results.get("messages", [])
    if not messages:
        return {"message": "No new job application emails found."}

    fetched_applications = []


    for msg in messages:
        full_msg = service.users().messages().get(userId="me", id=msg["id"]).execute()
        
        payload = full_msg['payload']
        headers = payload['headers']
        for header in headers:
            if header['name'] == 'Date':
                email_date = header['value']
            elif header['name'] == 'Subject':
                email_subject = header['value']

        company = extract_company_spacy(email_subject)

        if company is None:
            company = extract_company(email_subject)
        
        fetched_applications.append({
            "id": full_msg["id"],
            "subject": email_subject,
            "company": company,
            "date": email_date
        })
    
    return {"message": "Emails fetched successfully", "applications": fetched_applications} 