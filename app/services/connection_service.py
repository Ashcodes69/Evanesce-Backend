from sqlalchemy.orm import Session
from app.models.connection import Connection


def get_ordered_pair(user_id_1: int, user_id_2: int):
    return (user_id_1, user_id_2) if user_id_1 < user_id_2 else (user_id_2, user_id_1)


def get_connection(db: Session, user_id_1: int, user_id_2: int) -> Connection | None:
    user_a_id, user_b_id = get_ordered_pair(user_id_1, user_id_2)

    return (
        db.query(Connection)
        .filter(Connection.user_a_id == user_a_id, Connection.user_b_id == user_b_id)
        .first()
    )
