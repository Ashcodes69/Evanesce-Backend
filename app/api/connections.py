from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.models.connection import Connection
from app.schemas.connection_schema import ConnectionRequest
from app.services.auth_service import get_current_user
from app.services.connection_service import get_connection, get_ordered_pair

router = APIRouter()


@router.post("/connections/request")
def send_connection_request(
    payload: ConnectionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    target_id = payload.target_user_id

    if target_id == current_user.id:
        raise HTTPException(
            status_code=400, detail="you cannot send request to yourself"
        )

    target_user = db.query(User).filter(User.id == target_id).first()

    if not target_user:
        raise HTTPException(status_code=404, detail="user not found")

    existing = get_connection(db, current_user.id, target_id)

    if existing:
        if existing.status == "accepted":
            raise HTTPException(status_code=400, detail="you are already connected")
        if existing.status == "pending":
            raise HTTPException(status_code=400, detail="A request is already pending")
        if existing.status == "blocked":
            raise HTTPException(status_code=404, detail="user not found")

    user_a_id, user_b_id = get_ordered_pair(current_user.id, target_id)

    new_connection = Connection(
        user_a_id=user_a_id,
        user_b_id=user_b_id,
        status="pending",
        requested_by=current_user.id,
    )

    db.add(new_connection)
    db.commit()
    db.refresh(new_connection)

    return {"message": "Connection request sent", "connection_id": new_connection.id}


@router.post("/connections/{connection_id}/accept")
def accept_connection_request(
    connection_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    connection = db.query(Connection).filter(Connection.id == connection_id).first()

    if not connection:
        raise HTTPException(status_code=404, detail="request not found")
    if connection.requested_by == current_user.id:
        raise HTTPException(
            status_code=403, detail="you cannot accept your own request"
        )
    if current_user.id not in (connection.user_a_id, connection.user_b_id):
        raise HTTPException(status_code=403, detail="Not authorized for this request")
    if connection.status != "pending":
        raise HTTPException(status_code=400, detail="this status is no longer pending")

    connection.status = "accepted"
    db.commit()
    db.refresh(connection)

    return {"message": "Connection accepted", "connection_id": connection.id}


@router.post("/connections/{connection_id}/reject")
def reject_connection_request(
    connection_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    connection = db.query(Connection).filter(Connection.id == connection_id).first()

    if not connection:
        raise HTTPException(status_code=404, detail="request not found")
    if connection.requested_by == current_user.id:
        raise HTTPException(
            status_code=403, detail="You cannot reject your own request"
        )
    if current_user.id not in (connection.user_a_id, connection.user_b_id):
        raise HTTPException(status_code=403, detail="Not authorized for this request")
    if connection.status != "pending":
        raise HTTPException(status_code=400, detail="This request is no longer pending")

    connection.status = "blocked"
    connection.blocked_by = current_user.id
    db.commit()
    db.refresh(connection)

    return {"message": "Request rejected"}


@router.post("/connections/{target_user_id}/block")
def block_user(
    target_user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    connection = get_connection(db, current_user.id, target_user_id)

    if not connection:
        raise HTTPException(status_code=404, detail="No connection with this user")
    if current_user.id not in (connection.user_a_id, connection.user_b_id):
        raise HTTPException(status_code=403, detail="not authorized")
    if connection.status == "blocked":
        raise HTTPException(status_code=400, detail="Already blocked")

    connection.status = "blocked"
    connection.blocked_by = current_user.id
    db.commit()

    return {"message": "User blocked"}


@router.post("/connections/{target_user_id}/unblock")
def unblock_user(
    target_user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    connection = get_connection(db, current_user.id, target_user_id)

    if not connection:
        raise HTTPException(status_code=404, detail="No connection with this user")
    if current_user.id not in (connection.user_a_id, connection.user_b_id):
        raise HTTPException(status_code=403, detail="not authorized")
    if connection.status != "blocked":
        raise HTTPException(status_code=400, detail="this user is not blocked")
    if connection.blocked_by != current_user.id:
        raise HTTPException(status_code=403, detail="you did not blocked this user")

    db.delete(connection)
    db.commit()

    return {"message": "User unblocked"}


@router.get("/connections/requests/incoming")
def get_incomming_requests(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    connections = (
        db.query(Connection)
        .filter(
            (
                (Connection.user_a_id == current_user.id)
                | (Connection.user_b_id == current_user.id)
            ),
            Connection.status == "pending",
            Connection.requested_by != current_user.id,
        )
        .all()
    )
    results = []

    for cnn in connections:
        other_id = cnn.user_b_id if cnn.user_a_id == current_user.id else cnn.user_a_id
        other_user = db.query(User).filter(User.id == other_id).first()
        if other_user:
            results.append(
                {
                    "connection_id": cnn.id,
                    "user_id": other_user.id,
                    "username": other_user.username,
                    "full_name": other_user.full_name,
                }
            )

    return results


@router.get("/connections/blocked")
def blocked_users(
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user)
):
    connections = (
        db.query(Connection)
        .filter(
            (
                (Connection.user_a_id == current_user.id)
                | (Connection.user_b_id == current_user.id)
            ),
            Connection.status == "blocked",
            Connection.blocked_by == current_user.id,
        )
        .all()
    )

    results = []
    for cnn in connections:
        other_user_id = (
            cnn.user_b_id if cnn.user_a_id == current_user.id else cnn.user_a_id
        )
        other_user = db.query(User).filter(User.id == other_user_id).first()

        if other_user:
            results.append(
                {
                    "user_id": other_user.id,
                    "username": other_user.username,
                    "full_name": other_user.full_name,
                }
            )
    return results
