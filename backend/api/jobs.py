from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.core.dependencies import get_current_user
from backend.db.session import get_db
from backend.models.db_users import User
from backend.models.schema import ApplicationCreate, ApplicationOut, EditApplicationOut
from datetime import datetime, timezone
from backend.service.jobs_service import *


router = APIRouter( tags=["Jobs"])

@router.post("/create", response_model=ApplicationOut)
def create_job(job: ApplicationCreate, db: Session = Depends(get_db), curr_user: User = Depends(get_current_user)):
    time = datetime.now(timezone.utc)
    return create_job_service(db, curr_user.id, job, time)
    

@router.patch("/update", response_model=EditApplicationOut)
def update_user_job(job: EditApplication, db: Session = Depends(get_db), curr_user: User = Depends(get_current_user)):
    job_id = find_job(db, curr_user.id, job.company, job.position)
    return update_job_application(db, job_id, job)


@router.get("/list")
def list_user_jobs(db: Session = Depends(get_db), curr_user: User = Depends(get_current_user)):
    jobs =  list_jobs(db, curr_user.id)
    return {"message": "fetched!", "applications": jobs}
