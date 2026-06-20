from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.message import Message
from app.models.user import User
from app.schemas.message_schema import MessageCreate, MessageResponce
from app.services.auth_service import get_current_user

router = APIRouter()

# ============== route for send message =========================
@router.post("/send-message", response_model=MessageResponce)
def send_message(
    message: MessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    new_message = Message(
        sender_id=current_user.id,
        receiver_id=message.receiver_id,
        content=message.content,
    )

    db.add(new_message)
    db.commit()
    db.refresh(new_message)

    return new_message

# ================== route to fetch message =================
@router.get("/messages/{user_id}")
def get_messages(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    message = (
        db.query(Message)
        .filter(
            (
                (Message.sender_id == current_user.id) & 
                (Message.receiver_id == user_id))
            | (
                (Message.sender_id == user_id) & 
                (Message.receiver_id == current_user.id)
            )
        )
        .all()
    )

    return message
