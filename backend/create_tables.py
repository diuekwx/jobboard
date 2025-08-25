from backend.db.session import engine
from backend.db.base_class import Base
from backend.models import db_users, db_application, db_response, db_event

def create_all_tables():
    Base.metadata.create_all(bind=engine)
    print("Tables created successfully.")

if __name__ == "__main__":
    create_all_tables()