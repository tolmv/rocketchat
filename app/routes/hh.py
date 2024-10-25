import re
from fastapi import APIRouter, Request, Response, HTTPException
import aiohttp
import json
import asyncio
import requests
import gspread
import config
from telethon import events
from telethon.errors import (
    UserDeactivatedBanError,
    UserBlockedError,
    PeerIdInvalidError,
)
from pydantic import BaseModel
from telethon.tl.types import PeerUser, InputPeerUser
from loguru import logger
from utils.token_manager import get_auth_token

import httpx

from utils.hhparse import (
    get_active_vacancies,
    get_negotiations,
    append_applicants_to_spreadsheet,
    get_telegram_id,
    async_request_hh
)
from utils.spreadsheets_api import (
    get_all_clients,
    make_client_inactive,
    change_applicant_hr,
)

class EventPayload(BaseModel):
    employer_id: str
    negotiation_date: str
    resume_id: str
    topic_id: str
    vacancy_id: str

class WebhookData(BaseModel):
    action_type: str
    id: str
    payload: EventPayload
    subscription_id: str
    user_id: str

# Assuming that environment variables and clients initialization are handled elsewhere

gc = gspread.service_account(filename="valentinwm-tg-36da0854f6c0.json")
gs = gc.open_by_url(
    "https://docs.google.com/spreadsheets/d/19FbsRnpgitFa_opHy_oTIb_-9EIFERKTohkD3oS9u9A/edit#gid=0"
)

lock = asyncio.Lock()

sheet = gs.get_worksheet(0)

clients = get_all_clients(gs)

hh = APIRouter()

for i, client in clients.items():

    @client.on(events.NewMessage())
    async def start(event):
        sender_id = str(event.sender_id)
        column_values = sheet.col_values(4)
        row_index = column_values.index(str(sender_id)) + 1
        if row_index == 0:
            return

        all_messages = (
                (sheet.cell(row_index, 15).value or "") + f"\nApplicant: {event.text}"
        ).strip()
        sheet.update_cell(row_index, 15, all_messages)


@hh.post("/send_telegram")
async def send_telegram(request: Request):
    data = await request.json()

    row = int(data.get("row", None))
    msg = data.get("value", "")
    all_messages = (data.get("all_msges", "") + f"\nHR: {msg}").strip()
    metadata = data.get("metadata", "")
    telegram_id = int(data.get("telegram_id"))
    try:
        metadata = json.loads(metadata)
    except Exception as e:
        print(e)
        metadata = {}
    access_hash = int(metadata.get("access_hash", 0))

    print(clients)
    client = clients.get(int(metadata.get("tg_hr", -1)), None)

    if client is None:
        client = await change_applicant_hr(gs, row, clients, metadata, telegram_id)

    try:
        entity = await client.get_entity(PeerUser(int(telegram_id)))
    except ValueError:
        entity = await client.get_input_entity(
            InputPeerUser(int(telegram_id), access_hash=int(access_hash))
        )
    except (
            UserDeactivatedBanError,
            UserBlockedError,
            PeerIdInvalidError,
    ):  # TODO add more exceptions
        client = await change_applicant_hr(gs, row, clients, metadata, telegram_id)
        entity = await client.get_input_entity(
            InputPeerUser(int(telegram_id), access_hash=int(access_hash))
        )

    except Exception as e:
        print(e)
        return {"message": "Can't send message", "status": "error"}

    try:
        await client.send_message(entity, msg)
    except PeerIdInvalidError:
        client = await change_applicant_hr(gs, row, clients, metadata, telegram_id)
        await client.send_message(entity, msg)

    sheet.update_cell(row, 15, all_messages)
    sheet.update_cell(row, 16, "")


@hh.post("/update_clients")
async def update_clients(request: Request):
    global clients
    new_clients = get_all_clients(gs)

    for i, client in clients.items():
        await client.disconnect()

    clients = new_clients
    for i, client in clients.items():
        await client.start(phone=lambda: make_client_inactive(gs, i))


@hh.on_event("startup")
async def startup_event():
    for i, client in clients.items():
        try:
            await client.start(phone=lambda: make_client_inactive(gs, i))
            pass
        except Exception as e:
            print(e)

@hh.get("/parce_applications")
async def parce_applications(request: Request):
    async with lock:
        try:
            start_date = request.query_params.get("start_date", None)

            active_vacancies = get_active_vacancies()
            print(len(active_vacancies))
            with open("vacancies.json", "w", encoding="utf-8") as f:
                json.dump(active_vacancies, f, ensure_ascii=False, indent=4)
            for vacancy in active_vacancies:
                vacancy_id = vacancy["id"]
                print(vacancy_id, vacancy["name"])
                try:
                    negotiations = get_negotiations(vacancy_id, start_date)
                    spreadsheet_id = config.SHEET_KEY
                    await append_applicants_to_spreadsheet(
                        spreadsheet_id, negotiations, vacancy
                    )
                except Exception as e:
                    logger.exception(f"Error in parce_applications: {e}")

            return {"message": "applications parsed"}
        except Exception as e:
            return Response(e, status_code=500)

@hh.post("/new_negotiation")
async def new_negotiation(data: WebhookData):
    logger.info('start new_negotiation')
    negotiation_id = re.sub(r'notification\d*topic', '', data.id)
    vacancy_id = data.payload.vacancy_id

    logger.info(f"New negotiation: {negotiation_id} {vacancy_id}")
    
    headers = {"Authorization": f"Bearer {config.HH_TOKEN}", "User-Agent": "HH-User-Agent"}

    async with httpx.AsyncClient() as client:
        try:
            negotiation = await async_request_hh(client, f"https://api.hh.ru/negotiations/{negotiation_id}", headers=headers)
            
            if negotiation.status_code != 200:
                logger.exception(f"Negotiation not found")
                return {"error": "Negotiation not found"}, 404

            vacancy = await async_request_hh(client, f"https://api.hh.ru/vacancies/{vacancy_id}", headers=headers)

            if vacancy.status_code != 200:
                logger.exception(f"Vacancy not found")
                return {"error": "Vacancy not found"}, 404

            spreadsheet_id = config.SHEET_KEY
            await append_applicants_to_spreadsheet(spreadsheet_id, [negotiation.json()], vacancy.json())
            logger.info('added append_applicants_to_spreadsheet new_negotiation')
        except Exception as e:
            logger.exception(f"Error in new_negotiation: {e}")
            return {"error": str(e)}, 500

    logger.info('end new_negotiation')
    return {"message": "new negotiation added"}

async def async_request_hh(client, url, headers, retries=3):
    for attempt in range(retries):
        try:
            response = await client.get(url, headers=headers, timeout=10.0)  # Увеличение таймаута до 10 секунд
            response.raise_for_status()
            return response
        except httpx.ReadTimeout:
            if attempt < retries - 1:
                continue  # Попробовать еще раз
            else:
                raise  # Если исчерпаны все попытки, выбросить исключение
        except httpx.HTTPStatusError as e:
            raise e


@hh.post("/enrich_telegram_ids")
async def enrich_telegram_ids(request: Request):
    data = await request.json()
    row = int(data.get("row", None))

    SESSION_STRING = data.get("session_string", None)
    APP_ID = data.get("app_id", None)
    APP_HASH = data.get("app_hash", None)

    cell = sheet.cell(row, 7).value
    telegram_id = sheet.cell(row, 4).value
    if telegram_id:
        return {"message": "Telegram ID already exists"}
    metadata = sheet.cell(row, 25).value

    try:
        metadata = json.loads(metadata)
    except Exception as e:
        print(e)
        metadata = {}

    cleared_cell = (
        cell.replace(" ", "")
        .replace("-", "")
        .replace("(", "")
        .replace(")", "")
        .replace("'", "")
    )
    tg_id, access_hash = await get_telegram_id(
        cleared_cell, SESSION_STRING, APP_ID, APP_HASH
    )
    metadata["access_hash"] = access_hash

    sheet.update_cell(row, 4, tg_id)
    sheet.update_cell(row, 25, json.dumps(metadata))


# TODO: remove it
@hh.get("/request_token")
async def request_token():
    status = await get_auth_token()
    return {"message": "token requested", "status": status}


@hh.get("/send_code")
async def recieve_code(code: str):
    post_data = {
        "grant_type": "authorization_code",
        "client_id": config.CLIENT_ID,
        "client_secret": config.CLIENT_SECRET,
        "code": code
    }

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "User-Agent": "api-test-agent"
    }

    async with aiohttp.ClientSession() as session:
        try:
            response = await session.post(url=config.ACCESS_TOKEN_ENDPOINT,
                                          data=post_data,
                                          headers=headers)

            response_data = await response.json()
            logger.info(response_data)
            if 'error' in response_data:
                logger.error(f"recieve_token: Can't recieve access token:\n{response_data}")
                raise HTTPException(status_code=500, detail=f"Can't recieve access token: {response_data['error']}")

            return response_data

        except Exception as e:
            logger.error(f"recieve_token: \n{e}")
            raise HTTPException(status_code=500, detail=f"{e}")


        except Exception as e:
            logger.exception(f"recieve_token: \n{e}")
            raise HTTPException(status_code=500, detail=f"{e}")
