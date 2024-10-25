from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse

from sqlalchemy import select, update
from db.models import *
from db.db_connect import async_session

from pydantic import BaseModel
from loguru import logger
from datetime import datetime

chats = APIRouter()


@chats.get("/")
async def get_chats():
    async with async_session() as session:
        try:
            stmt = select(Instances)
            logger.debug(stmt)
            res = await session.execute(stmt)
            logger.debug(res)
            instances = res.scalars().all()  # Get all instances

            chat_list = [instances.to_dict() for instances in instances]

            return JSONResponse(content=chat_list)
        except Exception as e:
            logger.exception(e)
            return JSONResponse(
                content={"error": str(e)},
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


@chats.get("/{id}")
async def get_messages(id: int):
    async with async_session() as session:
        try:
            result = await session.execute(
                select(Prompts).where(Prompts.instance_id == id)
            )
            messages = result.scalars().all()
            return JSONResponse(content=[message.to_dict() for message in messages])
        except Exception as e:
            logger.exception(e)
            return JSONResponse(
                content=str(e), status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class MessageData(BaseModel):
    text: str


@chats.post("/{chat_id}")
async def create_message(chat_id: int, message_data: MessageData):
    async with async_session() as session:
        try:
            # Mark existing prompts as inactive
            await session.execute(
                update(Prompts)
                .where(Prompts.instance_id == chat_id)
                .values(is_active=False)
            )

            # Create a new prompt/message
            new_message = Prompts(
                text=message_data.text,
                date=datetime.now(),
                instance_id=chat_id,
                is_active=True,
            )
            session.add(new_message)
            await session.commit()
            await session.refresh(new_message)

            return JSONResponse(
                content=new_message
            )  # Assuming a to_dict method in your model
        except Exception as e:
            logger.exception(e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
            )
