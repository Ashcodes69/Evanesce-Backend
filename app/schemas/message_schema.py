from pydantic import BaseModel

class MessageCreate(BaseModel):
    content: str
    receiver_id: int

class MessageResponce(BaseModel):
    id: int
    sender_id: int
    receiver_id: int
    content: str

    class config:
        from_attributes = True