import random, hashlib, hmac, os
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.models.otp import OtpCode
from app.core.email import send_email
from app.core.security import hash_email

OTP_HASH_SECRET = os.getenv("OTP_HASH_SECRET").encode()
OTP_EXPIRY_MINUTES = 10
OTP_RESET_COOLDOWN_SECONDS = 60


def hash_code(code: str) -> str:
    return hmac.new(OTP_HASH_SECRET, code.encode(), hashlib.sha256).hexdigest()


def generate_otp() -> str:
    return f"{random.randint(0, 999999):06d}"


def can_request_otp(db: Session, email: str, purpose: str) -> bool:
    email_hash = hash_email(email)

    recent = (
        db.query(OtpCode)
        .filter(OtpCode.email_hash == email_hash, OtpCode.purpose == purpose)
        .order_by(OtpCode.created_at.desc())
        .first()
    )

    if not recent:
        return True

    elapsed = (datetime.now() - recent.created_at).total_seconds()
    return elapsed >= OTP_RESET_COOLDOWN_SECONDS


def send_otp(db: Session, email: str, purpose: str):
    code = generate_otp()
    email_hash = hash_email(email)

    otp_row = OtpCode(
        email_hash=email_hash,
        code_hash=hash_code(code),
        purpose=purpose,
        expires_at=datetime.now() + timedelta(minutes=OTP_EXPIRY_MINUTES),
        consumed=False,
    )

    db.add(otp_row)
    db.commit()

    subject = "Your evanesce verification code"
    body = f"Your verification code is {code}. It expires in {OTP_EXPIRY_MINUTES} minutes."

    send_email(email, subject, body)


def verify_otp(db: Session, email: str, code: str, purpose: str) -> bool:
    email_hash = hash_email(email)
    code_hash = hash_code(code)

    otp_row = (
        db.query(OtpCode)
        .filter(
            OtpCode.email_hash == email_hash,
            OtpCode.code_hash == code_hash,
            OtpCode.purpose == purpose,
            OtpCode.consumed == False,
        )
        .order_by(OtpCode.created_at.desc())
        .first()
    )

    if not otp_row:
        return False
    if otp_row.expires_at < datetime.now():
        return False

    otp_row.consumed = True
    db.commit()

    return True
