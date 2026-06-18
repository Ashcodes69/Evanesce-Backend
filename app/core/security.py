from passlib.context import CryptContext

from cryptography.fernet import Fernet
from dotenv import load_dotenv
import os

# passward hashing
pwd_context = CryptContext(
    schemes=['bcrypt'],
    deprecated='auto'
)

def hash_password(password: str):
    return pwd_context.hash(password)

# Encrypting Phone number

load_dotenv()

cipher = Fernet(os.getenv('ENCRYPTION_KEY'))

def encrypt_phone(phone: str):
    return cipher.encrypt(phone.encode()).decode()

def decrypt_phone(encrypted_phone: str):
    return cipher.decrypt(encrypted_phone.encode()).decode()

# compairing users given password to its hashed password
def verify_password(plain_password: str, hashed_password: str):
    return pwd_context.verify(plain_password, hashed_password)
