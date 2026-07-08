from sqlalchemy import Column, DateTime, Integer, String
from app.db.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    last_seen = Column(DateTime, nullable=True)

    username = Column(String, unique=True, nullable=False)
    full_name = Column(String, nullable=False)

    encrypted_email = Column(String, nullable=False)
    hashed_email = Column(String, unique=True, nullable=False, index=True)

    hashed_password = Column(String, nullable=False)