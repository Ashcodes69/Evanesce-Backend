from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.message import Message


router = APIRouter()
active_connection = {}


@router.websocket("/ws/{user_id}")
async def websoket_endpoint(websoket: WebSocket, user_id: int):
    await websoket.accept()

    active_connection[user_id] = websoket
    db: Session = SessionLocal()

    try:
        while True:
            data = await websoket.receive_json()
            receiver_id = data["receiver_id"]
            message_text = data["message"]

            # save message in db
            new_message = Message(
                sender_id=user_id, receiver_id=receiver_id, content=message_text
            )
            db.add(new_message)
            db.commit()

            if receiver_id in active_connection:
                receiver_soket = active_connection[receiver_id]

                await receiver_soket.send_json(
                    {"from": user_id, "message": message_text}
                )

    except WebSocketDisconnect:
        del active_connection[user_id]

    finally:
        db.close()
