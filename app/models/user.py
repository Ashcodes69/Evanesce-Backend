from sqlalchemy import Column, DateTime, Integer, String
from app.db.database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    encrypted_phone_number = Column(String, unique=True, nullable=False)
    last_seen = Column(DateTime, nullable=True)