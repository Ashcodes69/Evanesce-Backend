from passlib.context import CryptContext
from cryptography.fernet import Fernet
import os
from jose import jwt, JWTError
from datetime import datetime, timedelta, timezone
from fastapi.security import OAuth2PasswordBearer
import hmac
import hashlib

from dotenv import load_dotenv

# ================passward hashing ====================

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str):
    return pwd_context.hash(password)


# =============== Encrypting emailr=================

load_dotenv()

cipher = Fernet(os.getenv("ENCRYPTION_KEY"))

EMAIL_HASH_SECRET = os.getenv("EMAIL_HASH_SECRET").encode()


def hash_email(email: str):
    return hmac.new(
        EMAIL_HASH_SECRET, email.lower().strip().encode(), hashlib.sha256
    ).hexdigest()


def encrypt_email(email: str):
    return cipher.encrypt(email.lower().strip().encode()).decode()


def decrypt_email(encrypted_email: str):
    return cipher.decrypt(encrypted_email.encode()).decode()


# ===== compairing users given password to its hashed password =====


def verify_password(plain_password: str, hashed_password: str):
    return pwd_context.verify(plain_password, hashed_password)


# ================== create access token ==========================
SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = os.getenv("ALGORITHM")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES"))


def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, ALGORITHM)

    return encoded_jwt


def verify_token(token: str):
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")

        if username is None:
            return None
        return username

    except JWTError:
        return None


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")
