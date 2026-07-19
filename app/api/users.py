from fastapi.security import OAuth2PasswordRequestForm
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.user import User
from app.schemas.user_schema import (
    UserCreate,
    UserPublic,
    UserSearchResult,
    ChangeFullName,
    ChangeUsername,
    VerifyResetIdentity,
    ResetPassword,
)
from app.core.security import (
    hash_email,
    encrypt_email,
    hash_password,
    verify_password,
    create_access_token,
    create_reset_token,
    verify_reset_token,
)
from app.api.websocket import active_connection
from app.services.auth_service import get_current_user
from app.services.connection_service import get_connection

router = APIRouter()


# ================= route for user creation ====================
@router.post("/register")
def register(user: UserCreate, db: Session = Depends(get_db)):
    email_hash = hash_email(user.email)
    existing = db.query(User).filter(User.hashed_email == email_hash).first()
    if existing:
        raise HTTPException(status_code=400, detail="email already registered")

    new_user = User(
        username=user.username,
        full_name=user.full_name,
        encrypted_email=encrypt_email(user.email),
        hashed_email=hash_email(user.email),
        hashed_password=hash_password(user.password),
    )

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    access_token = create_access_token({"sub": user.username})

    return {
        "message": "user created",
        "access_token": access_token,
        "token_type": "bearer",
    }


@router.post("/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)
):

    user = db.query(User).filter(User.username == form_data.username).first()

    if not user:
        raise HTTPException(status_code=401, detail="Invalid username")

    if not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Invalid password")

    access_token = create_access_token({"sub": user.username})

    return {"access_token": access_token, "token_type": "bearer"}


# ==================== get the current logged in user details ============
@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "full_name": current_user.full_name,
    }


# ===================== route for search a user ================
@router.get("/users/search/{username}", response_model=UserSearchResult)
def search_user(
    username: str,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    response.headers["Cache-Control"] = "no-store"

    user = db.query(User).filter(User.username == username).first()

    if user is None:
        raise HTTPException(status_code=404, detail="user not found")
    if user.id == current_user.id:
        raise HTTPException(status_code=403, detail="you cannot search yourself")

    connection = get_connection(db, current_user.id, user.id)

    if not connection or connection.status == "blocked":
        raise HTTPException(status_code=404, detail="user not found")
    elif connection.status == "accepted":
        status = "accepted"
    elif connection.status == "pending":
        status = (
            "pending_sent"
            if connection.requested_by == current_user.id
            else "pending_received"
        )

    return {
        "id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "connection_status": status,
    }


@router.get("/users/{user_id}", response_model=UserPublic)
def get_user_by_id(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


# ================ route to check the users online/ofline status ==========
@router.get("/users/status/{user_id}")
def get_user_status(user_id: int):
    if user_id in active_connection:
        return {"status": "online"}
    return {"status": "offline"}


# =============== route to get user last seen ====================
@router.get("/users/last-seen/{user_id}")
def get_last_seen(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.id == user_id).first()
    return {"last_seen": user.last_seen}


@router.put("/me/full-name")
def change_full_name(
    payload: ChangeFullName,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    current_user.full_name = payload.full_name
    db.commit()
    return {"message": "full name changed"}


@router.put("/me/username")
def change_username(
    payload: ChangeUsername,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not verify_password(payload.password, current_user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect password")

    existing = db.query(User).filter(User.username == payload.new_username).first()

    if existing:
        raise HTTPException(status_code=400, detail="username already exists")

    current_user.username = payload.new_username
    db.commit()
    return {"message": "username updated please log in again"}


@router.post("/auth/verify-reset-identity")
def verify_reset_identity(payload: VerifyResetIdentity, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).first()

    if not user or user.hashed_email != hash_email(payload.email):
        raise HTTPException(status_code=400, detail="inncorrect username or email")

    reset_token = create_reset_token(user.username)
    return {"reset_token": reset_token}


@router.post("/auth/reset-password")
def reset_password(payload: ResetPassword, db: Session = Depends(get_db)):
    username = verify_reset_token(payload.reset_token)
    if not username:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="user not found")

    user.hashed_password = hash_password(payload.new_password)
    db.commit()
    return{"message": "Password updated Please log in again"}