from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.message import Message
from app.models.user import User
from app.core.security import verify_token


router = APIRouter()
active_connection = {}


@router.websocket("/ws")
async def websoket_endpoint(websoket: WebSocket):
    token = websoket.query_params.get("token")
    if not token:
        await websoket.close(code=1000)
        return

    username = verify_token(token)
    if username is None:
        await websoket.close(code=1000)
        return

    db: Session = SessionLocal()

    user = db.query(User).filter(User.username == username).first()
    if not user:
        await websoket.close(code=1000)
        return

    user_id = user.id

    await websoket.accept()

    active_connection[user_id] = websoket
    db: Session = SessionLocal()

    try:
        while True:
            data = await websoket.receive_json()
            receiver_id = int(data["receiver_id"])
            message_text = data["message"]

            # save message in db
            new_message = Message(
                sender_id=user_id,
                receiver_id=receiver_id,
                content=message_text,
                status="sent",
            )
            db.add(new_message)
            db.commit()
            db.refresh(new_message)
            print("Connected users:", active_connection.keys())
            print("Receiver:", receiver_id, type(receiver_id))
            if receiver_id in active_connection:

                new_message.status = 'delivered'
                db.commit()
                db.refresh(new_message)

                receiver_soket = active_connection[receiver_id]

                await receiver_soket.send_json({
                    'message_id': new_message.id,
                    'from': user_id,
                    'message': message_text,
                    'status': new_message.status
                })

    except WebSocketDisconnect:
        del active_connection[user_id]

    finally:
        db.close()
