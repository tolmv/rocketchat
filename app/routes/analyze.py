import io

from fastapi import HTTPException
import openai
import json

import pdfplumber
import requests
from openai.types.beta.threads import Message
import httpx
import config
from typing import Optional, Dict, Any, Union
from loguru import logger
"""import logging

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
"""


def punctuation_assistant(ascii_transcript: str = "", json_mode: bool = False) -> str:
    client_open_ai = openai.OpenAI(api_key=config.OPENAI_HR_API_KEY)
    try:
        # Создаем поток
        thread = client_open_ai.beta.threads.create()
        #logger.info(f"Thread created with ID: {thread.id}")

        # Добавляем сообщение в поток
        message = client_open_ai.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content="Dialogue: [Dialogue]".replace('[Dialogue]', ascii_transcript)
        )
        #logger.info(f"Message added to thread ID: {thread.id}")

        # Создаем и выполняем запуск
        run = client_open_ai.beta.threads.runs.create_and_poll(
            thread_id=thread.id,
            assistant_id=config.ASSISTANT_ID_PUNCTUATION,
        )
        #logger.info(f"Run status: {run.status}")

        if run.status == 'completed':
            # Получаем список сообщений
            messages = client_open_ai.beta.threads.messages.list(
                thread_id=thread.id
            )
            #logger.info(f"Messages retrieved from thread ID: {thread.id}")
            return messages.data[0].content[0].text.value
        else:
            logger.error("Run did not complete successfully")
            return f"Run status: {run.status}"
    except Exception as e:
        logger.exception(f"An error occurred during the API call. {e}")
        return "Error"


def create_list_questions(resume, name_vacancy, vacancy: str = "", json_mode: bool = False) -> str:
    client_open_ai = openai.OpenAI(api_key=config.OPENAI_HR_API_KEY)
    try:
        # Создаем поток
        thread = client_open_ai.beta.threads.create()
        #logger.info(f"Thread created with ID: {thread.id}")

        # Добавляем сообщение в поток
        message = client_open_ai.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content="Name of Vacancy: [Name of Vacancy], Vacancy: [Vacancy], Resume: [Resume]".replace('[Resume]', resume).replace('[Name of Vacancy]', name_vacancy).replace('[Vacancy]', vacancy)
        )
        #logger.info(f"Message added to thread ID: {thread.id}")

        # Создаем и выполняем запуск
        run = client_open_ai.beta.threads.runs.create_and_poll(
            thread_id=thread.id,
            assistant_id=config.ASSISTANT_CREATE_QUESTIONS,
        )
        #logger.info(f"Run status: {run.status}")

        if run.status == 'completed':
            # Получаем список сообщений
            messages = client_open_ai.beta.threads.messages.list(
                thread_id=thread.id
            )
            #logger.info(f"Messages retrieved from thread ID: {thread.id}")
            return messages.data[0].content[0].text.value
        else:
            logger.error("Run did not complete successfully")
            return f"Run status: {run.status}"
    except Exception as e:
        logger.exception(f"An error occurred during the API call. {e}")
        return "Error"


def call_status(ascii_transcript: str = "", json_mode: bool = False) -> Message | str:
    client_open_ai = openai.OpenAI(api_key=config.OPENAI_HR_API_KEY)
    try:
        # Создаем поток
        thread = client_open_ai.beta.threads.create()

        # Добавляем сообщение в поток
        message = client_open_ai.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content="Converted text from call: [Text]".replace('[Text]', ascii_transcript)
        )

        # Создаем и выполняем запуск
        run = client_open_ai.beta.threads.runs.create_and_poll(
            thread_id=thread.id,
            assistant_id=config.ASSISTANT_CALL_STATUS,
        )

        if run.status == 'completed':
            # Получаем список сообщений
            messages = client_open_ai.beta.threads.messages.list(
                thread_id=thread.id
            )
            return messages.data[0].content[0].text.value
        else:
            logger.info("Error punctuation_assistant")
            return f"Run status: {run.status}"
    except Exception as e:
        logger.exception(f"An error occurred during the API call. {e}")
        return "Error"


def analyze_hr(dialogue: str, resume: str, vacancy: str) -> Message | str:
    client_open_ai = openai.OpenAI(api_key=config.OPENAI_HR_API_KEY)
    try:
        # Создаем поток
        thread = client_open_ai.beta.threads.create()

        # Добавляем сообщение в поток
        message = client_open_ai.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content="Dialogue: [Dialogue], Vacancy: [Vacancy], [Resume]".replace('[Dialogue]', dialogue).replace('[Resume]', dialogue).replace("[Vacancy]", vacancy)
        )

        # Создаем и выполняем запуск
        run = client_open_ai.beta.threads.runs.create_and_poll(
            thread_id=thread.id,
            assistant_id=config.ASSISTANT_ID_HR,
        )

        if run.status == 'completed':
            # Получаем список сообщений
            messages = client_open_ai.beta.threads.messages.list(
                thread_id=thread.id
            )
            return messages.data[0].content[0].text.value
        else:
            logger.info("Error analyze_hr")
            return f"Run status: {run.status}"
    except Exception as e:
        logger.exception(f"An error occurred during the API call. {e}")
        return "Error"

def fetch_pdf_from_url(url):
    response = requests.get(url)
    response.raise_for_status()  # Проверка на наличие ошибок при скачивании
    return response.content


def pdf_to_text(pdf_data):
    try:
        text = ''
        with pdfplumber.open(io.BytesIO(pdf_data)) as pdf:
            for page in pdf.pages:
                text += page.extract_text() + '\n'
        return text
    except:
        return "PDF not found"


def recognize_speech(buffer):
    return requests.post(
        "https://api.openai.com/v1/audio/transcriptions",
        data={
            "model": "whisper-1",
        },
        files={"file": (f"voice_file.mp3", buffer, f"audio/mp3")},
        headers={"Authorization": f"Bearer {config.OPENAI_SALES_API_KEY}"},
    ).json().get("text")
    
def get_cv_score(ascii_transcript):
    client_open_ai = openai.OpenAI(api_key=config.OPENAI_HR_API_KEY)
    try:
        # Создаем поток
        thread = client_open_ai.beta.threads.create()

        # Добавляем сообщение в поток
        message = client_open_ai.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content="Converted text from call: [Text]".replace('[Text]', ascii_transcript)
        )

        # Создаем и выполняем запуск
        run = client_open_ai.beta.threads.runs.create_and_poll(
            thread_id=thread.id,
            assistant_id=config.ASSISTANT_CV_SCORE,
        )

        if run.status == 'completed':
            # Получаем список сообщений
            messages = client_open_ai.beta.threads.messages.list(
                thread_id=thread.id
            )
            return messages.data[0].content[0].text.value
        else:
            logger.info("Error punctuation_assistant")
    except Exception as e:
        logger.exception(f"An error occurred during the API call. {e}")
        return "Error"
