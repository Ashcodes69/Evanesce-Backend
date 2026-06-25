from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.db.session import get_db
from app.models.message import Message
from app.models.user import User
from app.services.auth_service import get_current_user
from app.schemas.message_schema import MessageResponse, ConversationResponse

router = APIRouter()


# ================== route to fetch message =================
@router.get("/messages/{user_id}", response_model=list[MessageResponse])
def get_messages(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    messages = (
        db.query(Message)
        .filter(
            ((Message.sender_id == current_user.id) & (Message.receiver_id == user_id))
            | (
                (Message.sender_id == user_id)
                & (Message.receiver_id == current_user.id)
            )
        )
        .order_by(Message.created_at.asc())
        .all()
    )

    return messages


@router.get("/conversations", response_model=list[ConversationResponse])
def get_conversations(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    messages = (
        db.query(Message)
        .filter(
            or_(
                Message.sender_id == current_user.id,
                Message.receiver_id == current_user.id,
            )
        )
        .order_by(Message.created_at.desc())
        .all()
    )

    conversations = {}

    for msg in messages:
        other_user_id = (
            msg.receiver_id if msg.sender_id == current_user.id else msg.sender_id
        )

        if other_user_id not in conversations:
            user = db.query(User).filter(User.id == other_user_id).first()

            conversations[other_user_id] = {
                "user_id": user.id,
                "username": user.username,
                "last_message": msg.content,
                "created_at": msg.created_at,
                "unread_msg_count": (
                    db.query(Message)
                    .filter(
                        Message.sender_id == other_user_id,
                        Message.receiver_id == current_user.id,
                        Message.status != "seen",
                    )
                    .count()
                ),
            }
    return list(conversations.values())


@router.put("/messages/seen/{user_id}")
def mark_messages_seen(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    messages = (
        db.query(Message)
        .filter(
            Message.sender_id == user_id,
            Message.receiver_id == current_user.id,
            Message.status == "delivered",
        )
        .order_by(Message.created_at.asc())
        .all()
    )

    if not messages:
        return {"message": "no delivered message found"}

    for msg in messages:
        msg.status = "seen"

    db.commit()

    return {"message": "message updated", "count": len(messages)}
