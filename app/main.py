# uvicorn app.main:app --reload
from fastapi import FastAPI

from app.models.user import User
from app.models.message import Message

from app.db.database import Base, engine
from app.api.users import router as user_router
from app.api.messages import router as message_router
from app.api.websocket import router as websoket_router


Base.metadata.create_all(bind=engine)

app = FastAPI()

app.include_router(user_router)
app.include_router(message_router)
app.include_router(websoket_router)

@app.get('/')
def root():
    return {'message': 'hello YOU!'}