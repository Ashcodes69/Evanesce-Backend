from datetime import datetime, timezone
from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Index,
    String,
)

from app.db.database import Base


class FileTransfer(Base):
    __tablename__ = "file_transfers"

    __table_args__ = (
        Index(
            "ix_file_transfers_status_expires_at",
            "status",
            "expires_at",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    sender_id = Column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    receiver_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True
    )
    storage_key = Column(
        String, unique=True, nullable=False, index=True
    )
    size_bytes = Column(BigInteger, nullable=False)
    status = Column(String, nullable=False, default="pending")
    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    expires_at = Column(DateTime(timezone=True), nullable=False)
    downloaded_at = Column(DateTime(timezone=True), nullable=True)
