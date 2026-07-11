from pydantic import BaseModel

class ConnectionRequest(BaseModel):
    target_user_id: int