from sqlalchemy.orm import Session
from fastapi import HTTPException
from backend.models.db_application import Application
from datetime import datetime
import uuid
from backend.models.schema import EditApplication, ApplicationCreate

def create_job_service(db: Session, user_id: uuid.UUID, data: ApplicationCreate):
    # position maybe
    exisiting_job = db.query(Application).filter(Application.company_name == data.company,
                                                 
                                                 Application.user_id == user_id).first()
    if exisiting_job:
        raise HTTPException(status_code=400, detail="Job already added")
    new_job = Application(user_id = user_id, 
                          company_name= data.company, 
                          position = data.position, 
                          status= data.status, 
                          application_date = data.time)
    db.add(new_job)
    db.commit()
    db.refresh(new_job)
    return new_job

def find_job(db: Session, user_id: uuid.UUID, company: str,  position: str):
        job = db.query(Application).filter(Application.company_name == company,
                                                 Application.position == position,
                                                 Application.user_id == user_id).first()
        return job.id

def update_job_application(db: Session, app_id: uuid.UUID, data: EditApplication, user_id: uuid.UUID):
    app = db.query(Application).filter(Application.id == app_id, Application.user_id == user_id).first()
    if not app:
        raise HTTPException(status_code=404, detail="Application not found")

    update_data = data.model_dump(exclude_unset=True) 
    for key, value in update_data.items():
        setattr(app, key, value)

    db.commit()
    db.refresh(app)
    return app

def list_jobs(db: Session, id: uuid):
    jobs = db.query(Application).filter(Application.user_id == id).all()
    return jobs

 