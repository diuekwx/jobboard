from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from backend.db.session import get_db
from backend.api.user import router as user_router
from backend.api.jobs import router as job_router
from backend.api.oatuh import router as gmail_router
import os 
from starlette.middleware.sessions import SessionMiddleware


app = FastAPI(title="J*b")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(
    SessionMiddleware,
    secret_key = os.getenv("SESSION_SECRET_KEY")
)


app.include_router(user_router, prefix="/api") 
app.include_router(job_router, prefix="/job") 
app.include_router(gmail_router, prefix="/gmail")

@app.get("/")
def read_root():
    return {"message": "J*b!"}
