import io

from fastapi import HTTPException
import openai
import json

import requests
from openai.types.beta.threads import Message

import config
from typing import Optional, Dict, Any, Union
from loguru import logger

def recognize_speech(buffer):
    return requests.post(
        "https://api.openai.com/v1/audio/transcriptions",
        data={
            "model": "whisper-1",
        },
        files={"file": (f"voice_file.mp3", buffer, f"audio/mp3")},
        headers={"Authorization": f"Bearer {config.OPENAI_SALES_API_KEY}"},
    ).json().get("text")

def punctuation_assistant(ascii_transcript: str = "", json_mode: bool = False) -> str:
    client_open_ai = openai.OpenAI(api_key=config.OPENAI_SALES_API_KEY)
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
            assistant_id=config.ASSISTANT_SALES_ROLES,
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
    client_open_ai = openai.OpenAI(api_key=config.OPENAI_SALES_API_KEY)
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
            assistant_id=config.ASSISTANT_CALL_STATUS_SALES,
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
