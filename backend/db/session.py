from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv
import os

load_dotenv()

database_url = os.getenv("DATABASE_URL")


engine = create_engine(database_url)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

from backend.db.base_class import Base


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()