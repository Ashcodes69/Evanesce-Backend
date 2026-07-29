from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.api.websocket import active_connection
from app.core.security import (
    create_access_token,
    create_reset_token,
    encrypt_email,
    hash_email,
    hash_password,
    verify_password,
    verify_reset_token,
    create_signup_token,
    verify_signup_token,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.user_schema import (
    ChangeFullName,
    ChangeUsername,
    ResetPassword,
    UserPublic,
    UserSearchResult,
    VerifyResetIdentity,
    RequestSignupOtp,
    VerifySignupOtp,
    CheckUsername,
    CompleteSignup,
    VerifyResetOtp,
)
from app.services.auth_service import get_current_user
from app.services.connection_service import get_connection
from app.services.otp_service import (
    can_request_otp,
    send_otp,
    verify_otp,
)

router = APIRouter()


# ================= route for user creation ====================
@router.post("/auth/signup/request-otp")
def request_signup_otp(
    payload: RequestSignupOtp, db: Session = Depends(get_db)
):
    email_hash = hash_email(payload.email)
    existing = (
        db.query(User).filter(User.hashed_email == email_hash).first()
    )

    if existing:
        raise HTTPException(
            status_code=400, detail="email already registered"
        )

    if not can_request_otp(db, payload.email, purpose="signup"):
        raise HTTPException(
            status_code=403,
            detail="please wait before requesting another code",
        )

    send_otp(db, payload.email, purpose="signup")

    return {"message": "verification code sent"}


@router.post("/auth/signup/verify-otp")
def verify_signup_otp(
    payload: VerifySignupOtp, db: Session = Depends(get_db)
):
    is_valid = verify_otp(
        db, payload.email, payload.code, purpose="signup"
    )

    if not is_valid:
        raise HTTPException(
            status_code=400, detail="Invalid or Expired code"
        )

    signup_token = create_signup_token(payload.email)
    return {"signup_token": signup_token}


@router.post("/auth/signup/check-username")
def check_username(
    payload: CheckUsername, db: Session = Depends(get_db)
):
    existing = (
        db.query(User)
        .filter(User.username == payload.username)
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=400, detail="username already exists"
        )

    return {"available": True}


@router.post("/auth/signup/complete")
def complete_signup(
    payload: CompleteSignup, db: Session = Depends(get_db)
):
    email = verify_signup_token(payload.signup_token)
    if not email:
        raise HTTPException(
            status_code=400,
            detail="invalid or expired signup session",
        )

    existing_email = (
        db.query(User)
        .filter(User.hashed_email == hash_email(email))
        .first()
    )
    if existing_email:
        raise HTTPException(
            status_code=400, detail="email already registered"
        )

    existing_username = (
        db.query(User)
        .filter(User.username == payload.username)
        .first()
    )
    if existing_username:
        raise HTTPException(
            status_code=400, detail="username already taken"
        )

    new_user = User(
        username=payload.username,
        full_name=payload.full_name,
        hashed_password=hash_password(payload.password),
        encrypted_email=encrypt_email(email),
        hashed_email=hash_email(email),
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    access_token = create_access_token({"sub": new_user.username})

    return {
        "message": "account created",
        "access_token": access_token,
        "token_type": "bearer",
    }


@router.post("/login")
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):

    user = (
        db.query(User)
        .filter(User.username == form_data.username)
        .first()
    )

    if not user:
        raise HTTPException(
            status_code=401, detail="Invalid username"
        )

    if not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=401, detail="Invalid password"
        )

    access_token = create_access_token({"sub": user.username})

    return {"access_token": access_token, "token_type": "bearer"}


# ==================== get the current logged in user details ========
@router.get("/me")
def get_me(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "username": current_user.username,
        "full_name": current_user.full_name,
    }


# ===================== route for search a user ================
@router.get(
    "/users/search/{username}", response_model=UserSearchResult
)
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
        raise HTTPException(
            status_code=403, detail="you cannot search yourself"
        )

    connection = get_connection(db, current_user.id, user.id)

    if connection and connection.status == "blocked":
        raise HTTPException(status_code=404, detail="user not found")
    elif connection and connection.status == "accepted":
        status = "accepted"
    elif connection and connection.status == "pending":
        status = (
            "pending_sent"
            if connection.requested_by == current_user.id
            else "pending_received"
        )
    else:
        status = "none"

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


# ================ route to check the users online/offline status ==========
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
    if not verify_password(
        payload.password, current_user.hashed_password
    ):
        raise HTTPException(
            status_code=401, detail="Incorrect password"
        )

    existing = (
        db.query(User)
        .filter(User.username == payload.new_username)
        .first()
    )

    if existing:
        raise HTTPException(
            status_code=400, detail="username already exists"
        )

    current_user.username = payload.new_username
    db.commit()
    return {"message": "username updated please log in again"}


@router.post("/auth/verify-reset-identity")
def verify_reset_identity(
    payload: VerifyResetIdentity, db: Session = Depends(get_db)
):
    user = (
        db.query(User)
        .filter(User.username == payload.username)
        .first()
    )

    if not user or user.hashed_email != hash_email(payload.email):
        raise HTTPException(
            status_code=400, detail="Invalid username or email"
        )

    if not can_request_otp(
        db, payload.email, purpose="password_reset"
    ):
        raise HTTPException(
            status_code=429,
            detail="please wait before requesting another code",
        )

    send_otp(db, payload.email, purpose="password_reset")

    return {"message": "verification code sent"}


@router.post("/auth/verify-reset-otp")
def verify_reset_otp(
    payload: VerifyResetOtp, db: Session = Depends(get_db)
):
    is_valid = verify_otp(
        db, payload.email, payload.code, purpose="password_reset"
    )
    if not is_valid:
        raise HTTPException(
            status_code=400, detail="invalid or expired code"
        )

    reset_token = create_reset_token(payload.username)
    return {"reset_token": reset_token}


@router.post("/auth/reset-password")
def reset_password(
    payload: ResetPassword, db: Session = Depends(get_db)
):
    username = verify_reset_token(payload.reset_token)
    if not username:
        raise HTTPException(
            status_code=400, detail="Invalid or expired reset link"
        )

    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise HTTPException(status_code=404, detail="user not found")

    user.hashed_password = hash_password(payload.new_password)
    db.commit()
    return {"message": "Password updated Please log in again"}
