from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from backend.core.dependencies import get_current_user
from backend.db.session import get_db
from backend.models.db_users import User
from backend.models.schema import (
    ApplicationCreate, ApplicationOut, EditApplication, EditApplicationOut,
    MergeApplication,
)
from backend.service.jobs_service import create_job_service, list_jobs, update_job_application
from backend.service.workflow_service import (
    application_history, archive_application, merge_applications, undo_action,
)


router = APIRouter(tags=["Jobs"])


@router.post("/create", response_model=ApplicationOut)
def create_job(
    job: ApplicationCreate,
    db: Session = Depends(get_db),
    curr_user: User = Depends(get_current_user),
):
    return create_job_service(db, curr_user.id, job)


@router.patch("/{application_id}", response_model=EditApplicationOut)
def update_user_job(
    application_id: UUID,
    job: EditApplication,
    db: Session = Depends(get_db),
    curr_user: User = Depends(get_current_user),
):
    return update_job_application(db, application_id, job, curr_user.id)


@router.get("/list")
def list_user_jobs(
    db: Session = Depends(get_db), curr_user: User = Depends(get_current_user)
):
    return {"message": "fetched!", "applications": list_jobs(db, curr_user.id)}


@router.get("/archived")
def list_archived_jobs(
    db: Session = Depends(get_db), curr_user: User = Depends(get_current_user)
):
    return {"applications": list_jobs(db, curr_user.id, archived=True)}


@router.get("/review")
def review_queue(
    db: Session = Depends(get_db), curr_user: User = Depends(get_current_user)
):
    return {
        "applications": [row for row in list_jobs(db, curr_user.id) if row["needs_review"]]
    }


@router.post("/{application_id}/review/correct", response_model=EditApplicationOut)
def correct_review(
    application_id: UUID,
    correction: EditApplication,
    db: Session = Depends(get_db),
    curr_user: User = Depends(get_current_user),
):
    return update_job_application(
        db, application_id, correction, curr_user.id, resolve_review=True
    )


@router.post("/{application_id}/archive")
def archive_job(
    application_id: UUID,
    db: Session = Depends(get_db),
    curr_user: User = Depends(get_current_user),
):
    app = archive_application(db, curr_user.id, application_id, True)
    return {"id": str(app.id), "archived": True}


@router.post("/{application_id}/restore")
def restore_job(
    application_id: UUID,
    db: Session = Depends(get_db),
    curr_user: User = Depends(get_current_user),
):
    app = archive_application(db, curr_user.id, application_id, False)
    return {"id": str(app.id), "archived": False}


@router.post("/{application_id}/review/merge")
def merge_review(
    application_id: UUID,
    merge: MergeApplication,
    db: Session = Depends(get_db),
    curr_user: User = Depends(get_current_user),
):
    action = merge_applications(db, curr_user.id, application_id, merge.target_id)
    return {"action_id": str(action.id), "merged_into": str(merge.target_id)}


@router.post("/actions/{action_id}/undo")
def undo_user_action(
    action_id: UUID,
    db: Session = Depends(get_db),
    curr_user: User = Depends(get_current_user),
):
    action = undo_action(db, curr_user.id, action_id)
    return {"id": str(action.id), "undone": True}


@router.get("/{application_id}/history")
def job_history(
    application_id: UUID,
    db: Session = Depends(get_db),
    curr_user: User = Depends(get_current_user),
):
    return {"history": application_history(db, curr_user.id, application_id)}


@router.get("/export/data")
def export_user_data(
    db: Session = Depends(get_db), curr_user: User = Depends(get_current_user)
):
    applications = list_jobs(db, curr_user.id) + list_jobs(db, curr_user.id, archived=True)
    for app in applications:
        app["history"] = application_history(db, curr_user.id, UUID(app["id"]))
    response = JSONResponse({
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "account": {"email": curr_user.email},
        "applications": applications,
    })
    response.headers["Content-Disposition"] = 'attachment; filename="job-data-export.json"'
    return response
