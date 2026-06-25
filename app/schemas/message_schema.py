from pydantic import BaseModel
from datetime import datetime

class MessageCreate(BaseModel):
    content: str
    receiver_id: int

class MessageResponse(BaseModel):
    id: int
    sender_id: int
    receiver_id: int
    content: str
    status: str
    created_at: datetime


    class config:
        from_attributes = True

class ConversationResponse(BaseModel):
    user_id: int
    username: str
    last_message: str
    created_at: datetime
    unread_msg_count: int