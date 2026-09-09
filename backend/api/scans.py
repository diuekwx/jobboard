from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from backend.core.dependencies import get_current_user
from backend.db.session import get_db
from backend.models.db_integrationtokens import IntegrationToken
from backend.models.db_users import User
from backend.service.scan_job_service import (
    create_scan_job,
    get_user_scan_job,
    latest_scan_job,
    serialize_scan_job,
)


router = APIRouter(tags=["Gmail scans"])


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def start_scan(
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    connected = db.query(IntegrationToken.id).filter(
        IntegrationToken.user_id == current_user.id,
        IntegrationToken.provider == "gmail",
    ).first()
    if not connected:
        raise HTTPException(status_code=409, detail="Gmail is not connected")

    job, created = create_scan_job(db, current_user.id)
    if not created:
        response.status_code = status.HTTP_200_OK
    return serialize_scan_job(job)


@router.get("/current")
def current_scan(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = latest_scan_job(db, current_user.id)
    return serialize_scan_job(job) if job else None


@router.get("/{job_id}")
def scan_status(
    job_id: UUID,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = get_user_scan_job(db, current_user.id, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Scan not found")
    return serialize_scan_job(job)
