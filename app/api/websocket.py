from datetime import datetime, timezone
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.models.message import Message
from app.models.user import User
from app.core.security import verify_token
from app.services.connection_service import get_connection


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
    if user_id in active_connection:
        old_socket = active_connection[user_id]
        await old_socket.close()

    active_connection[user_id] = websoket

    for other_id, other_socket in active_connection.items():
        if other_id != user_id:
            await other_socket.send_json(
                {"type": "presence", "user_id": user_id, "status": "online"}
            )

    pending_messages = (
        db.query(Message)
        .filter(Message.receiver_id == user_id, Message.status == "sent")
        .order_by(Message.created_at.asc())
        .all()
    )
    for msg in pending_messages:
        msg.status = "delivered"

        await websoket.send_json(
            {
                "message_id": msg.id,
                "from": msg.sender_id,
                "message": msg.content,
                "status": msg.status,
                "created_at": str(msg.created_at),
            }
        )
        db.commit()

    try:
        while True:
            data = await websoket.receive_json()
            receiver_id = int(data["receiver_id"])
            event = data.get("type", "message")

            if event == "typing":
                connection = get_connection(db, user_id, receiver_id)

                if (
                    connection
                    and connection.status == "accepted"
                    and receiver_id in active_connection
                ):
                    receiver_soket = active_connection[receiver_id]
                    await receiver_soket.send_json({"from": user_id, "type": "typing"})
                continue
            message_text = data["message"]

            connection = get_connection(db, user_id, receiver_id)
            if not connection or connection.status != "accepted":
                await websoket.send_json(
                    {"type": "error", "detail": "you are not connected with this user"}
                )
                continue

            new_message = Message(
                sender_id=user_id,
                receiver_id=receiver_id,
                content=message_text,
                status="sent",
            )
            db.add(new_message)
            db.commit()
            db.refresh(new_message)

            if receiver_id in active_connection:
                new_message.status = "delivered"
                db.commit()
                db.refresh(new_message)

                receiver_soket = active_connection[receiver_id]

                await receiver_soket.send_json(
                    {
                        "message_id": new_message.id,
                        "from": user_id,
                        "message": message_text,
                        "status": new_message.status,
                        "created_at": str(new_message.created_at),
                    }
                )

    except WebSocketDisconnect:
        user.last_seen = datetime.now(timezone.utc)
        db.commit()
        del active_connection[user_id]

        for other_id, other_socket in active_connection.items():
            await other_socket.send_json(
                {
                    "type": "presence",
                    "user_id": user_id,
                    "status": "offline",
                    "last_seen": str(user.last_seen),
                }
            )

    finally:
        db.close()
