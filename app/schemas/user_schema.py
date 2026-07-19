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
    full_name: str

    class Config:
        from_attributes = True

class UserSearchResult(BaseModel):
    id: int
    username: str
    full_name: str
    connection_status: str

    class Config:
        from_attributes = True


class ChangeFullName(BaseModel):
    full_name: str

class ChangeUsername(BaseModel):
    password: str
    new_username: str

class VerifyResetIdentity(BaseModel):
    username: str
    email: EmailStr

class ResetPassword(BaseModel):
    reset_token: str
    new_password: str