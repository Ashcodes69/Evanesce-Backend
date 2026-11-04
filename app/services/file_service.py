import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_

from app.db.session import SessionLocal
from app.models.file_transfer import FileTransfer
from app.models.message import Message
from app.services.storage_service import StorageError, delete_blob

logger = logging.getLogger(__name__)

CLEANUP_INTERVAL_SECONDS = 30
# safety delay between a reported download and deleting the stored file
DOWNLOADED_GRACE = timedelta(seconds=60)


async def run_file_cleanup_sweeper():
    from app.api.websocket import active_connection

    while True:
        db = SessionLocal()
        try:
            now = datetime.now(UTC)

            # Finished downloads (after the grace period) and transfers that
            # expired without being downloaded.
            transfers = (
                db.query(FileTransfer)
                .filter(
                    or_(
                        and_(
                            FileTransfer.status == "downloaded",
                            FileTransfer.downloaded_at <= now - DOWNLOADED_GRACE,
                        ),
                        and_(
                            FileTransfer.status == "pending",
                            FileTransfer.expires_at <= now,
                        ),
                    )
                )
                .all()
            )

            for transfer in transfers:
                # 1. Delete the stored file first. If that fails, keep the row
                #    so the next sweep retries instead of orphaning the blob.
                try:
                    await asyncio.to_thread(delete_blob, transfer.storage_key)
                except StorageError:
                    logger.error(
                        "Could not delete blob for transfer %s, will retry",
                        transfer.id,
                    )
                    continue

                # 2. The key message must not outlive the file it unlocks.
                message = None
                if transfer.message_id:
                    message = (
                        db.query(Message)
                        .filter(Message.id == transfer.message_id)
                        .first()
                    )

                notify = []
                if message:
                    notify = [message.id, message.sender_id, message.receiver_id]
                    db.delete(message)
                db.delete(transfer)
                db.commit()

                # 3. Tell open chats to drop the card.
                if notify:
                    message_id, sender_id, receiver_id = notify
                    payload = {"type": "message_deleted", "message_id": message_id}
                    for user_id in (sender_id, receiver_id):
                        if user_id in active_connection:
                            await active_connection[user_id].send_json(payload)

        except Exception:
            logger.exception("file cleanup sweeper error")
        finally:
            db.close()

        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)