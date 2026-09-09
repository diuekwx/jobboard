from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.api.user import router as user_router
from backend.api.jobs import router as job_router
from backend.api.oatuh import router as gmail_router
from backend.api.gmail import router as gmail_endpoint_router
from backend.api.sync import router as sync_router
from backend.api.scans import router as scans_router
import os 
from starlette.middleware.sessions import SessionMiddleware
from backend.core.config import cookie_secure, cors_origins, validate_security_config
from backend.core.security_middleware import SecurityMiddleware

validate_security_config()

app = FastAPI(title="J*b")



app.add_middleware(SecurityMiddleware)
app.add_middleware(
    SessionMiddleware,
    secret_key=os.environ["SESSION_SECRET_KEY"],
    session_cookie="oauth_session",
    max_age=600,
    same_site="lax",
    https_only=cookie_secure(),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(user_router, prefix="/api") 
app.include_router(job_router, prefix="/job") 
app.include_router(gmail_router, prefix="/gmail")
app.include_router(gmail_endpoint_router, prefix="/gmail-service")
app.include_router(sync_router, prefix="/sync")
app.include_router(scans_router, prefix="/gmail-service/scans")


@app.get("/")
def read_root():
    return {"message": "J*b!"}
