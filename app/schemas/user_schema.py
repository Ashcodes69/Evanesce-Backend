from pydantic import BaseModel, EmailStr


class RequestSignupOtp(BaseModel):
    email: EmailStr


class VerifySignupOtp(BaseModel):
    email: EmailStr
    code: str


class CheckUsername(BaseModel):
    username: str


class CompleteSignup(BaseModel):
    signup_token: str
    username: str
    password: str
    full_name: str


class UserLogin(BaseModel):
    username: str
    password: str


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


class VerifyResetOtp(BaseModel):
    username: str
    email: EmailStr
    code: str


class VerifyResetIdentity(BaseModel):
    username: str
    email: EmailStr


class ResetPassword(BaseModel):
    reset_token: str
    new_password: str
