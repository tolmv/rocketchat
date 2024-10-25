from fastapi import APIRouter, HTTPException, status
from fastapi.responses import JSONResponse

from sqlalchemy import select, update
from db.models import *
from db.db_connect import async_session

from pydantic import BaseModel, Field

config = APIRouter()


class AgentConfig(BaseModel):
    prompt: str = Field(None)
    model: str = Field(None)
    temperature: float = Field(None)


@config.post("/set_agent_config/{chat_id}")
async def set_agent_config(chat_id: int, agent_config: AgentConfig):
    async with async_session() as session:
        try:
            update_data = agent_config.model_dump(exclude_none=True)

            await session.execute(
                update(Instances).where(Instances.id == chat_id).values(**update_data)
            )
            await session.commit()

            return JSONResponse(content=update_data)
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
            )


@config.get("/get_agent_config/{chat_id}")
async def get_agent_config(chat_id: int):
    async with async_session() as session:
        try:
            result = await session.execute(
                select(Instances).where(Instances.id == chat_id)
            )
            instance = result.scalar_one_or_none()

            if not instance:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Instance not found"
                )

            result = await session.execute(
                select(Prompts)
                .where(Prompts.instance_id == chat_id)
                .order_by(Prompts.id.desc())
            )
            prompts = result.scalars().all()
            last_prompt = prompts[0] if prompts else None

            return JSONResponse(
                content={
                    "prompt": last_prompt.text if last_prompt else None,
                    "model": instance.model,
                    "temperature": instance.temperature,
                }
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
            )
