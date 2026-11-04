import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.file_transfer import FileTransfer
from app.models.message import Message
from app.models.user import User
from app.services.auth_service import get_current_user
from app.services.connection_service import get_connection
from app.services.massege_service import wake_sweeper
from app.services.storage_service import (
    FILE_CARD_LINGER_SECONDS,
    MAX_FILE_BYTES,
    MAX_PENDING_BYTES,
    TRANSFER_TTL,
    BlobNotFoundError,
    StorageError,
    cleanup_blob,
    download_blob,
    generate_storage_key,
    is_valid_dead_file,
    upload_blob,
)

logger = logging.getLogger(__name__)

router = APIRouter()


# ================== route to upload an encrypted file =================
@router.post("/files/upload", status_code=201)
def upload_file(
    receiver_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # 1. Authorization first, before reading any file bytes.
    #    Same rule as messaging: accepted connection only. A missing user,
    #    a stranger, and a blocked user all get the same answer.
    connection = get_connection(db, current_user.id, receiver_id)
    if not connection or connection.status != "accepted":
        raise HTTPException(
            status_code=400, detail="you are not connected with this user"
        )

    # 2. Read at most one byte over the cap. Never trust Content-Length.
    data = file.file.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise HTTPException(status_code=413, detail="file is too large")

    # 3. Format check: must look like one of our encrypted files.
    if not is_valid_dead_file(data):
        raise HTTPException(status_code=400, detail="invalid file format")

    # 4. Global storage budget across all pending transfers.
    pending_bytes = (
        db.query(func.coalesce(func.sum(FileTransfer.size_bytes), 0))
        .filter(FileTransfer.status == "pending")
        .scalar()
    )
    if pending_bytes + len(data) > MAX_PENDING_BYTES:
        raise HTTPException(
            status_code=503, detail="file storage is full, try again later"
        )

    # 5. Store the blob first, then the row.
    storage_key = generate_storage_key()
    try:
        upload_blob(storage_key, data)
    except StorageError:
        raise HTTPException(status_code=503, detail="culd not store the file")

    try:
        transfer = FileTransfer(
            sender_id=current_user.id,
            receiver_id=receiver_id,
            storage_key=storage_key,
            size_bytes=len(data),
            status="pending",
            expires_at=datetime.now(UTC) + TRANSFER_TTL,
        )
        db.add(transfer)
        db.commit()
        db.refresh(transfer)
    except Exception:
        db.rollback()
        cleanup_blob(storage_key)
        logger.exception("Could not save file transfer")
        raise HTTPException(status_code=500, detail="could not save the transfer")

    return {
        "id": transfer.id,
        "size_bytes": transfer.size_bytes,
        "expires_at": transfer.expires_at,
    }


# ================== route to download an encrypted file =================
@router.get("/files/{transfer_id}/download")
def download_files(
    transfer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    transfer = db.query(FileTransfer).filter(FileTransfer.id == transfer_id).first()

    # A missing transfer and someone else's transfer get the same answer,
    # so nobody can probe which transfer IDs exist.
    if not transfer or transfer.receiver_id != current_user.id:
        raise HTTPException(status_code=404, detail="file not found")

    # The receiver must still be connected to the sender.
    connection = get_connection(db, current_user.id, transfer.sender_id)
    if not connection or connection.status != "accepted":
        raise HTTPException(status_code=404, detail="file not found")

    if transfer.status != "pending" or transfer.expires_at <= datetime.now(UTC):
        raise HTTPException(status_code=410, detail="file is no longer avalable")

    try:
        data = download_blob(transfer.storage_key)
    except BlobNotFoundError:
        logger.error("Blob missing for transfer %s", transfer.id)
        raise HTTPException(status_code=404, detail="file not found")
    except StorageError:
        raise HTTPException(status_code=503, detail="could not retrieve this file")

    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        },
    )


# ================== route to report a finished download =================
@router.post("/files/{transfer_id}/complete")
def complete_file(
    transfer_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    transfer = db.query(FileTransfer).filter(FileTransfer.id == transfer_id).first()

    # Only the receiver can report completion.
    if not transfer or transfer.receiver_id != current_user.id:
        raise HTTPException(status_code=404, detail="file not found")

    # Reporting twice (a retry after a network error) is harmless.
    if transfer.status == "downloaded":
        return {"status": "downloaded"}

    if transfer.status != "pending" or transfer.expires_at <= datetime.now(UTC):
        raise HTTPException(status_code=410, detail="file is no longer available")

    transfer.status = "downloaded"
    transfer.downloaded_at = datetime.now(UTC)

    # Shorten the file message's timer so the card disappears shortly after.
    # The existing sweeper then deletes it and notifies both users.
    if transfer.message_id:
        message = db.query(Message).filter(Message.id == transfer.message_id).first()
        if message:
            message.status = "seen"
            message.seen_at = datetime.now()
            message.disappear_delay_seconds = FILE_CARD_LINGER_SECONDS

    db.commit()
    wake_sweeper()
    return {"status": "downloaded"}
