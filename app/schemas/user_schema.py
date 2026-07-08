from pydantic import BaseModel, EmailStr

# ========= User for the batabase =============
class UserCreate(BaseModel):
    username: str
    full_name: str
    email: EmailStr
    password: str

# ============== user for the login ==============
class UserLogin(BaseModel):
    username: str
    password: str

# ============= user for searching ================
class UserPublic(BaseModel):
    id: int
    username: str

    class Config:
        from_attributes = True