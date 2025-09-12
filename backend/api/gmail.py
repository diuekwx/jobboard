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
from backend.service.jobs_service import create_job_service
from backend.service.sync_service import sync, get_last_updated, update_sync_after_fetch
from backend.models.schema import ApplicationCreate
from datetime import datetime, timezone

router = APIRouter(tags=["gmail"])

@router.get("/fetch-applications")
def fetch_job_applications(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
        
        #check synchronization 
        # if there is a time inside the db call this fetch first, if not call the other one first ?  
    last_updated = get_last_updated(db, current_user.id)
    search_after_timestamp: int

    if last_updated.last_synced_at:
        if isinstance(last_updated.last_synced_at, datetime):
            search_after_timestamp = int(last_updated.last_synced_at.timestamp())
        else:
            search_after_timestamp = int(last_updated.last_synced_at)

    else:
        # if they havent updated yet, use the start_day
        search_after_timestamp = int(last_updated.start_date.timestamp())

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
    query = f'in:inbox subject:("thank you for applying" OR "application received" OR "application submitted") after:{search_after_timestamp}'

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
                print(email_subject)
        
        company = extract_company_spacy(email_subject)

        if company is None:
            company = extract_company(email_subject)

        fetched_applications.append({
            "id": full_msg["id"],
            "company": company,
            "date": email_date,
            "status": "sent"
        })
        # obviously change inputs later
        job = ApplicationCreate(company=company, 
                                position="swe intern", 
                                status="sent", 
                                time=datetime.now(timezone.utc))
        create_job_service(db, current_user.id, job)

    
    update_sync_after_fetch(db, current_user.id)
    
    return {"message": "Emails fetched successfully", "applications": fetched_applications} 