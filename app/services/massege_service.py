import asyncio
from datetime import datetime, timezone

from app.db.session import SessionLocal
from app.models.message import Message


BASE_SECONDS = 3
PER_CHAR_SECONDS = 0.08
MIN_SECONDS = 5
MAX_SECONDS = 25

IDLE_SLEEP_SECONDS = 30  # how long to sleep if nothing is pending at all
sweep_trigger = asyncio.Event()  # lets other code wake the sweeper early


def calculate_disappear_delay(content: str) -> int:
    delay = BASE_SECONDS + len(content) * PER_CHAR_SECONDS
    return int(max(MIN_SECONDS, min(delay, MAX_SECONDS)))


def wake_sweeper():
    """Call this right after inserting/updating a message so the sweeper
    doesn't wait out a long idle sleep unnecessarily."""
    sweep_trigger.set()


async def run_disappear_sweeper():
    from app.api.websocket import active_connection
    while True:
        db = SessionLocal()
        next_wake = IDLE_SLEEP_SECONDS
        try:
            now = datetime.now()

            # --- Sweep 1: hide from sender ---
            sender_candidates = db.query(Message).filter(Message.hidden_from_sender == False).all()
            for msg in sender_candidates:
                delay = calculate_disappear_delay(msg.content)
                created = msg.created_at
                if created.tzinfo is not None:
                    created = created.replace(tzinfo=None)
                remaining = delay - (now - created).total_seconds()

                if remaining <= 0:
                    msg.hidden_from_sender = True
                    db.commit()
                    if msg.sender_id in active_connection:
                        await active_connection[msg.sender_id].send_json({
                            "type": "message_hidden_sender",
                            "message_id": msg.id,
                        })
                else:
                    next_wake = min(next_wake, remaining)

            # --- Sweep 2: hard delete once seen-timer runs out ---
            seen_candidates = db.query(Message).filter(
                Message.status == "seen", Message.seen_at.isnot(None)
            ).all()
            for msg in seen_candidates:
                delay = calculate_disappear_delay(msg.content)
                seen_at = msg.seen_at
                if seen_at.tzinfo is not None:
                    seen_at = seen_at.replace(tzinfo=None)
                remaining = delay - (now - seen_at).total_seconds()

                if remaining <= 0:
                    message_id, sender_id, receiver_id = msg.id, msg.sender_id, msg.receiver_id
                    db.delete(msg)
                    db.commit()
                    payload = {"type": "message_deleted", "message_id": message_id}
                    if sender_id in active_connection:
                        await active_connection[sender_id].send_json(payload)
                    if receiver_id in active_connection:
                        await active_connection[receiver_id].send_json(payload)
                else:
                    next_wake = min(next_wake, remaining)

        except Exception as e:
            print(f"disappear sweeper error: {e}")
        finally:
            db.close()
        sweep_trigger.clear()
        try:
            await asyncio.wait_for(sweep_trigger.wait(), timeout=max(1, next_wake))
        except asyncio.TimeoutError:
            pass  # normal case — timer expired, loop again to check

