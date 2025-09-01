from fastapi import FastAPI, UploadFile, File, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from backend.db.session import get_db
from backend.api.user import router as user_router
from backend.api.jobs import router as job_router

app = FastAPI(title="J*b")


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(user_router, prefix="/api") 
app.include_router(job_router, prefix="/job") 

@app.get("/")
def read_root():
    return {"message": "J*b!"}
