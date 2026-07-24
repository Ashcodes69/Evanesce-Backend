from sqlalchemy import Column, Integer, ForeignKey, Text, DateTime, String, Boolean, func
from app.db.database import Base
from datetime import datetime, timezone


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, index=True)

    sender_id = Column(Integer, ForeignKey("users.id"))
    receiver_id = Column(Integer, ForeignKey("users.id"))

    content = Column(Text, nullable=False)

    status = Column(String, default="sent")

    created_at = Column(DateTime, server_default=func.now(), default=lambda: datetime.now(timezone.utc))

    seen_at = Column(DateTime(timezone=True), nullable=True)
    hidden_from_sender = Column(Boolean, nullable=False, default=False)
