# uvicorn app.main:app --reload
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import asyncio

from app.models.user import User
from app.models.message import Message
from app.models.connection import Connection

from app.services.massege_service import run_disappear_sweeper

from app.db.database import Base, engine
from app.api.users import router as user_router
from app.api.messages import router as message_router
from app.api.websocket import router as websoket_router
from app.api.connections import router as connection_router


Base.metadata.create_all(bind=engine)

app = FastAPI()

app.include_router(user_router)
app.include_router(message_router)
app.include_router(websoket_router)
app.include_router(connection_router)


@app.get("/")
def root():
    return {"message": "hello YOU!"}


app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def start_background_tasks():
    asyncio.create_task(run_disappear_sweeper())
