from fastapi import FastAPI, status, HTTPException, WebSocket
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from sqlalchemy import select
from db.models import *
from db.db_connect import async_session

from typing import Optional, List, Any, Dict, Union
from pydantic import BaseModel

from loguru import logger

from utils.get_website_text import latest_sites
from utils.openaicustom import get_gpt_res
from utils.quiz import generate_quiz

from routes.chats import chats
from routes.config import config
from routes.spreadsheet import spreadsheet
from routes.transcriptionhr import transcriptionhr
from routes.hh import hh
from routes.transcriptionhr import contact_manager
from sales.routes.transcriptionsales import transcriptionsales


import time
import schedule
import asyncio
import threading
import uvicorn


app = FastAPI(title="GPT Mentor Editor Backend")

# Set up CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://gpt-mentor-editor-dev5.dev3.nekotal.com",
        "https://deliver.latoken.com/prompts/editor",
        "http://localhost:3000",
        "https://deliver.latoken.com",
        "https://mid.latoken.com",
        "http://mid.nekotal.com",
        "https://qa-equity.dev3.nekotal.com",
        "https://growth.dev3.nekotal.com",
        "http://latoken.com",
        "http://mid.nekotal.com:8090",
        "https://exchange3.tp.latoken.com",
        "https://landing3.tp.latoken.com",
        "https://latoken.com",
        "http://rocket-chat-fastapp.platform-ops-release.ra2-dev.nekotal.com",
        "http://10.42.0.0:33258",
        "http://116.203.85.210:1194",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chats, prefix="/chats", tags=["chats"])
app.include_router(config, prefix="/config", tags=["config"])
app.include_router(spreadsheet, prefix="/spreadsheet", tags=["spreadsheet"])
app.include_router(hh, prefix="/hh", tags=["hh"])
app.include_router(transcriptionhr, prefix="/transcriptionhr", tags=["transcriptionhr"])
app.include_router(transcriptionsales, prefix='/transcriptionsales', tags=["transcriptionsales"])


class InstanceData(BaseModel):
    name: str


@app.post("/create_instance")
async def create_instance(instance_data: InstanceData) -> JSONResponse:
    async with async_session() as session:
        try:
            new_instance = Instances(
                instance_name=instance_data.name,
                model="gpt-3.5-turbo-1106",
                temperature=0,
            )
            session.add(new_instance)
            await session.commit()
            await session.refresh(new_instance)
            return JSONResponse(
                status_code=status.HTTP_201_CREATED, content=new_instance.to_dict()
            )
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
            )


class QuizRequest(BaseModel):
    query: str
    num_questions: int


@app.post("/generate_quiz")
async def generate_quiz_endpoint(quiz_request: QuizRequest) -> JSONResponse:
    try:
        quiz = await generate_quiz(quiz_request.query, quiz_request.num_questions)
        return JSONResponse(status_code=status.HTTP_200_OK, content=quiz)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


class SummaryRequest(BaseModel):
    query: str


@app.post("/get_summary")
async def get_summary_endpoint(summary_request: SummaryRequest) -> JSONResponse:
    try:
        site = await latest_sites(summary_request.query)
        response = await get_gpt_res(
            f"Summarize the following text, which where contain on site {site}", site
        )
        return JSONResponse(content={"message": response})
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


class MentorAdviceRequest(BaseModel):
    query: str  # Assuming this is the structure of your request body
    message_id: Optional[str] = None
    data: Optional[dict] = None


class GPTOutput(BaseModel):
    user_id: int
    commitment_id: Optional[Union[int, str]] = None
    user_text: Optional[str] = None
    gpt_text: str
    model: str
    prompt: Optional[str] = None
    usage: Optional[Dict[str, Any]] = (
        None  # Correctly defined as an optional dictionary
    )
    execution_time: Optional[float] = None
    data: Optional[Any] = None
    message_id: Optional[str] = None


# Shared list for GPTOutput data
shared_gpt_output: List[GPTOutput] = []


@app.post("/get_mentor_advice/{agien}")
async def get_mentor_advice(agien: str, req: MentorAdviceRequest) -> JSONResponse:
    async with async_session() as session:
        try:
            start_time = time.perf_counter()
            logger.debug(f"Agien: {agien}\n" f"Request: {req}\n")

            try:
                stmt = select(Instances).where(Instances.id == int(agien))
            except:
                try:
                    stmt = select(Instances).where(Instances.instance_name == agien)
                except:
                    agien = agien.replace("_", " ")
                    stmt = select(Instances).where(Instances.instance_name == agien)

            instance = await session.scalar(stmt)

            if not instance:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Instance not found"
                )

            prompt = await session.execute(
                select(Prompts)
                .where(Prompts.instance_id == instance.id)
                .where(Prompts.instance_id == instance.id and Prompts.is_active is True)
            )
            prompt = prompt.scalar()

            if not prompt:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="Prompt not found"
                )

            prompt_text = prompt.text
            user_id = prompt.instance_id
            user_message = req.query
            if isinstance(agien, int):
                json_format = agien in [12, 18, 19]
            else:
                json_format = False
            agient_response = await get_gpt_res(
                prompt_text,
                user_message,
                instance.temperature,
                instance.model,
                json_format,
            )
            if agient_response is None:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Something went wrong with GPT response",
                )
            logger.debug(agient_response)
            end_time = time.perf_counter()
            usage = agient_response.usage if agient_response.usage else None

            execution_time = end_time - start_time
            logger.success(f"Execution time: {execution_time}")
            shared_gpt_output.append(
                GPTOutput(
                    user_id=user_id,
                    commitment_id=agien,
                    user_text=user_message,
                    gpt_text=agient_response.message_content,
                    model=agient_response.model,
                    prompt=agient_response.prompt,
                    usage=usage,
                    execution_time=execution_time,
                    data=req.data,
                    message_id=req.message_id,
                )
            )
            return JSONResponse(content={"message": agient_response.message_content})
        except Exception as e:
            logger.exception(e)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
            )


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            if shared_gpt_output:
                # Send data to the WebSocket client
                data = shared_gpt_output.pop(0)  # Get the first item from the list
                await websocket.send_json(data.model_dump())

            # Wait a bit before checking the list again
            await asyncio.sleep(1)
    except Exception as e:
        logger.exception(e)

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(1)

def run_scheduler():
    while True:
        schedule.run_pending()
        time.sleep(1)

async def get_all_contacts_async_wrapper():
    logger.info("Executing get_all_contacts_async")
    await asyncio.create_task(contact_manager.get_all_contacts_async())

def schedule_tasks():
    # Запланируйте задачи на выполнение в 03:00
    schedule.every().day.at("12:00").do(lambda: asyncio.run(get_all_contacts_async_wrapper()))
    schedule.every().day.at("00:00").do(lambda: asyncio.run(get_all_contacts_async_wrapper()))


if __name__ == "__main__":
    logger.info("Starting the application...")

    # Проверка текущего времени
    now = datetime.now()
    logger.info(f"Current server time: {now}")

    # Настроить планировщик задач
    schedule_tasks()

    # Запуск планировщика в отдельном потоке
    scheduler_thread = threading.Thread(target=run_scheduler)
    scheduler_thread.daemon = True
    scheduler_thread.start()
    uvicorn.run("main:app", host="0.0.0.0", port=8000)

