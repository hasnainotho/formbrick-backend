from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://pgadmin:secret@localhost:5432/formbricks')

# echo=True for debugging; keep False normally
engine = create_engine(DATABASE_URL, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

Base = declarative_base()

def init_db():
    # import models here to ensure they are registered on the metadata
    from . import models  # noqa: F401
    Base.metadata.create_all(bind=engine)
