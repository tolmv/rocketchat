import base64
import json
import requests
import asyncio
import time
import os
import shutil
import tarfile
import zipfile
import urllib.parse
import io
import pydub
import pdfplumber
import config

from fastapi import APIRouter, Request, Query, HTTPException
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime
from pydantic import BaseModel
from typing import List, Optional
from loguru import logger
from pydub import AudioSegment
from typing import List, Dict

spreadsheet = APIRouter()
creds = service_account.Credentials.from_service_account_file(
    "./data/service_account_file.json",
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)

service = build("sheets", "v4", credentials=creds)

spreadsheet_id = "19FbsRnpgitFa_opHy_oTIb_-9EIFERKTohkD3oS9u9A"
sheet_name = "Variables"
cell = "A1"

class AnsweringData(BaseModel):
    rows: List[int]
    values: List[str]
    all_msgs: List[str]
    profiles: List[str]


@spreadsheet.post("/answering")
async def answering(data: AnsweringData) -> None:
    try:
        from utils.openaicustom import get_gpt_res

        logger.debug(data)

        prompt_range = f"{config.PROMPT_SHEET}!A:AU"
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=config.SPREADSHEET_ID, range=prompt_range)
            .execute()
        )

        prompt_values = result.get("values", [])
        prompt_index = (
            prompt_values[0].index("Prompt Next Message")
            if "Prompt Next Message" in prompt_values[0]
            else None
        )
        prompt = prompt_values[1][prompt_index]

        sheet_values = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=config.SPREADSHEET_ID, range=f"{config.SHEET}!A:AU")
            .execute()
        ).get("values", [])
        next_message_index = (
            sheet_values[0].index("Next Message")
            if "Next Message" in sheet_values[0]
            else None
        )

        for i, row in enumerate(data.rows):
            content = json.dumps(
                {
                    "profile": data.profiles[i],
                    "all_messages": data.all_msgs[i],
                }
            )
            res = await get_gpt_res(prompt, content, model="gpt-4-turbo-preview")

            # Prepare the update for each iteration
            update_range = f"{config.SHEET}!{chr(65 + next_message_index)}{row}"
            update_body = {"values": [[res.message_content]]}

            # Execute the update for the current row
            try:
                service.spreadsheets().values().update(
                    spreadsheetId=config.SPREADSHEET_ID,
                    range=update_range,
                    valueInputOption="RAW",
                    body=update_body,
                ).execute()
            except Exception as error:
                logger.error(f"An error occurred: {error}")
    except Exception as e:
        logger.exception(e)


class ScoringData(BaseModel):
    rows: List[int]
    values: List[str]

def convert_to_default(cv_link):
    import re
    if cv_link and isinstance(cv_link, str):
        match = re.match(r'^https://drive\.google\.com/file/d/(.+)/view$', cv_link)
        if match and match.group(1):
            return f"https://drive.google.com/uc?id={match.group(1)}"
    else:
        print(f"cv_link {cv_link}")
    return cv_link

@spreadsheet.post("/scoring")
async def scoring(data: ScoringData) -> None:
    try:
        from utils.openaicustom import call_assistant
        from utils.agent_scoring import get_text_from_pdf

        logger.debug(data)

        prompt_range = f"{config.PROMPT_SHEET}!A:AU"

        for i, value in enumerate(data.values):
            try:
                response = requests.head(value)
                if response.status_code == 404:
                    raise HTTPException(status_code=404, detail=f"Файл не найден по указанному URL: {value}")
                
                avg_score = []
                dict_score = {}
                req = get_text_from_pdf(convert_to_default(value))
                logger.info('Processing PDF')

                for _ in range(3):
                    res = await call_assistant(req, json_mode=True)

                    if isinstance(res, list) and len(res) > 0:
                        assistant_message = next((msg for msg in res if msg.role == "assistant"), None)
                        if assistant_message:
                            message_content = "".join(block.text.value for block in assistant_message.content)
                            parsed_res = json.loads(message_content)
                            logger.debug(f"Parsed response: {parsed_res}")

                            if 'CV_score' in parsed_res:
                                logger.info(f'CV_score - {parsed_res["CV_score"]}')
                                avg_score.append(int(parsed_res["CV_score"]))
                                dict_score[parsed_res["CV_score"]] = parsed_res
                            else:
                                logger.error("Key 'CV_score' not found in the response")

                        else:
                            logger.error("No assistant message found in the response")
                    else:
                        logger.error("Invalid response structure from call_assistant")
                
                if avg_score:
                    real_score = min(dict_score.keys(), key=lambda k: abs(k - sum(avg_score) / 3))
                    parsed_res = dict_score[real_score]
                    cv_stack = ", ".join(parsed_res.get("CV_stack", []))

                    if cv_stack == "":
                        cv_stack = ""

                    cv_score = parsed_res.get("CV_score", "")
                    cv_summary = parsed_res.get("CV_summary", "")
                    role_best_match = parsed_res.get("role_best_match", "")

                    update_range = f"{config.SHEET}!R{data.rows[i]}:U{data.rows[i]}"
                    update_body = {
                        "values": [[cv_score, cv_stack, cv_summary, role_best_match]]
                    }
                    logger.info(f'Updating spreadsheet {update_range}')
                    service.spreadsheets().values().update(
                        spreadsheetId=config.SPREADSHEET_ID,
                        range=update_range,
                        valueInputOption="RAW",
                        body=update_body,
                    ).execute()
                else:
                    logger.error("No valid CV_score found after multiple attempts")
            except Exception as e:
                logger.exception(e)

    except Exception as e:
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e))


@spreadsheet.post("/scoring-sales")
async def scoringsales(data: ScoringData) -> None:
    try:
        from utils.openaicustom import call_assistant
        from utils.agent_scoring import get_text_from_pdf

        logger.debug(data)

        prompt_range = f"{config.PROMPT_SHEET}!A:AU"

        for i, value in enumerate(data.values):
            try:
                response = requests.head(value)
                if response.status_code == 404:
                    raise HTTPException(status_code=404, detail=f"Файл не найден по указанному URL: {value}")
                
                avg_score = []
                dict_score = {}
                req = get_text_from_pdf(convert_to_default(value))
                logger.info('Processing PDF')

                for _ in range(3):
                    res = await call_assistant(req, json_mode=True)

                    if isinstance(res, list) and len(res) > 0:
                        assistant_message = next((msg for msg in res if msg.role == "assistant"), None)
                        if assistant_message:
                            message_content = "".join(block.text.value for block in assistant_message.content)
                            parsed_res = json.loads(message_content)
                            logger.debug(f"Parsed response: {parsed_res}")

                            if 'CV_score' in parsed_res:
                                logger.info(f'CV_score - {parsed_res["CV_score"]}')
                                avg_score.append(int(parsed_res["CV_score"]))
                                dict_score[parsed_res["CV_score"]] = parsed_res
                            else:
                                logger.error("Key 'CV_score' not found in the response")

                        else:
                            logger.error("No assistant message found in the response")
                    else:
                        logger.error("Invalid response structure from call_assistant")
                
                if avg_score:
                    real_score = min(dict_score.keys(), key=lambda k: abs(k - sum(avg_score) / 3))
                    parsed_res = dict_score[real_score]
                    cv_stack = ", ".join(parsed_res.get("CV_stack", []))

                    if cv_stack == "":
                        cv_stack = ""

                    cv_score = parsed_res.get("CV_score", "")
                    cv_summary = parsed_res.get("CV_summary", "")
                    role_best_match = parsed_res.get("role_best_match", "")

                    update_range = f"{config.SHEET}!R{data.rows[i]}:U{data.rows[i]}"
                    update_body = {
                        "values": [[cv_score, cv_stack, cv_summary, role_best_match]]
                    }
                    logger.info(f'Updating spreadsheet {update_range}')
                    service.spreadsheets().values().update(
                        spreadsheetId=config.SPREADSHEET_ID,
                        range=update_range,
                        valueInputOption="RAW",
                        body=update_body,
                    ).execute()
                else:
                    logger.error("No valid CV_score found after multiple attempts")
            except Exception as e:
                logger.exception(e)

    except Exception as e:
        logger.exception(e)
        raise HTTPException(status_code=500, detail=str(e))

class MessageData(BaseModel):
    role: str
    text: str


class Gpt4oHistoryData(BaseModel):
    api_key: str
    assistant_id: str
    content: List[MessageData]


class Gpt4oData(BaseModel):
    api_key: str
    assistant_id: str
    role: str
    text: str


@spreadsheet.post("/gpt-4o-history")
async def gpt4o(data: Gpt4oHistoryData) -> None:
    from utils.openaicustom import call_assistant_history
    return await call_assistant_history(data.content, data.assistant_id, data.api_key)


@spreadsheet.post("/gpt-4o")
async def gpt4o(data: Gpt4oData) -> None:
    from utils.openaicustom import call_assistant_custom
    return await call_assistant_custom(data.text, data.role, data.assistant_id, data.api_key)

@spreadsheet.get("/whatsable")
def whatsable(
    phone_number: str = Query(..., description="Phone Number"),
    limit: int = Query(20, description="Limit")
):
    logger.info(f'log {phone_number}')
    url = "https://database-red.adalo.com/databases/79830bb1e563439aa5e7900053208375/tables/t_6sjxxgdasmq3hde2budnvkng8"
    api_filter = {
        "user_id": "8,096,932,960",
        "phone_number": phone_number
    }
    api_filter_encoded = base64.urlsafe_b64encode(json.dumps(api_filter).encode()).decode()

    params = {
        "appId": "f5026b9a-6b47-475b-a4df-1010c6795239",
        "componentId": "dw7lk5rf4rtvct2ep18p81g5q",
        "bindingIds": "4z1adymc4om08ce9jf6auhni7,6emxt9rv9wjyj4jq8yyl3yrn3",
        "imageMeta": "true",
        "evaluateBindings": "true",
        "include": "",
        "counts": "",
        "limit": str(limit),
        "api_filter": api_filter_encoded
    }
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "ru,en;q=0.9,en-GB;q=0.8,en-US;q=0.7",
        "authorization": "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9.eyJkYXRhYmFzZUlkIjoiNzk4MzBiYjFlNTYzNDM5YWE1ZTc5MDAwNTMyMDgzNzUiLCJhdXRoVG9rZW4iOiJleUpoYkdjaU9pSkJNalUyUzFjaUxDSmxibU1pT2lKQk1qVTJRMEpETFVoVE5URXlJaXdpZW1sd0lqb2lSRVZHSW4wLmRuUm14X2tZTDhzNWhJNmVBLXEzalk2aDB3Uk5wY1hqclI3bHU0NjM0WGpYc244YlVqNl9ZX1NQOVVxM0NOdDRNRW8zbzMwWmYzUzN1NTc1RFpIbE83Xzl1ZXFNYWpFci5panNFOGlKM1VicEJnNkZMVjNUbWlnLm8zaGRpVzNwR1d0Yll5Qk82ZUYxUjlnbGtxdldEOFhJbkVTWm5Vam9yNGtlNVV3ci1hZDlhZWdUTzdISU9UanJtSkgtTXkyYXJLSjU3MGduMy1FMDRES3BtSmhiTnpMb25wdjFuWXF4R2JWYk5sMG94dEk0T1QxSFJzRVhORHZCb3BuYW9EbkF4cFBySnZsdU4wTTd1QkpkVDhGMFRtaW9pemVvR1IwQ0JyYy5JZTVqc2xoSlhRNmVGVGlUMTBqOHhaNnoxUUFQejhENEVvalc0NS1KUWRvIiwiaWQiOjgwOTY5MzI5NjAsInVzZXJJZCI6ODA5NjkzMjk2MCwiaWF0IjoxNzE3NjQ3OTg4LCJleHAiOjE3MTkzNzU5ODgsImF1ZCI6Ijc5ODMwYmIxZTU2MzQzOWFhNWU3OTAwMDUzMjA4Mzc1In0.CuAJMR19MlspKxBn6up2Ea1jA_80O1uM5jng2vpHA15kw5oV43-7bT__Tv9vAOqRfClU0rJEwCUqOzEKI6ObxhZvkBOTu4TCPzn1lnthwTdTAzul6BMk-QYmVtyjDbMsQDLqC5Qf2roADbh4qSqPOGxGL6ow85kyBF3QNu9ujEZIZn4wf1CrJgR4EVYY_91xOdtaQL1333iKogcy_dfIdmNv5mmzbAGQ3O__VZBgJotzhvi9EA7tkK_MUa-AKriMb0bwNw4eTob3mMLMXnOGaCve3fZ5i7hJo1lzUubkYPyH2WtoEHnaUy-SZF8LzrNDbyak3rvY-vA5agsik0s6zg",
        "baggage": "sentry-transaction=Screen%3A%3Asetup,sentry-public_key=3864dd63adb84e56b929e71dbbd613da,sentry-trace_id=416c0459ffcd42f0b05cfd0c13968afa,sentry-sample_rate=0.01",
        "sec-ch-ua": "\"Not/A)Brand\";v=\"8\", \"Chromium\";v=\"126\", \"Microsoft Edge\";v=\"126\"",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": "\"Windows\"",
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "cross-site",
        "sentry-trace": "416c0459ffcd42f0b05cfd0c13968afa-b63aefd5dd2cc181-0",
        "Referer": "https://notifier.whatsable.app/"
    }

    response = requests.get(url, headers=headers, params=params)

    logger.info('response' + str(response.status_code)  + str(response.json()))

    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail="Error fetching data")
    return response.json()

@spreadsheet.get("/process-data")
async def process_data(threshold: int = 6213):
    import gspread
    gc = gspread.service_account(filename="valentinwm-tg-36da0854f6c0.json")
    gs = gc.open_by_url("https://docs.google.com/spreadsheets/d/19FbsRnpgitFa_opHy_oTIb_-9EIFERKTohkD3oS9u9A/edit#gid=0")
    sheet = gs.get_worksheet(0)

    expected_headers = ["Phone"]
    actual_headers = sheet.row_values(1)

    missing_headers = set(expected_headers) - set(actual_headers)
    if missing_headers:
        raise HTTPException(status_code=400, detail=f"Missing headers in the spreadsheet: {missing_headers}")

    data = sheet.get_all_records(expected_headers=expected_headers)
    if not data:
        raise HTTPException(status_code=404, detail="No data found in the spreadsheet.")

    messages_sent = []
    current_token = get_token_from_sheet()
    
    for idx, row in enumerate(data):
        try:
            row_number = idx + 2
            phone_number = row.get('Phone')
            if not phone_number or row_number <= threshold:
                continue

            logger.info(f"Processing row {row_number} with phone number: {phone_number}")

            api_data = whatsable(phone_number, 20)
            if api_data is None:
                continue
            
            messages_content = [item['messages_content'] for item in api_data if 'messages_content' in item]
            logger.info(f"Messages content: {messages_content}")
            
            if not messages_content:
                continue

            for message in messages_content:
                if not message.strip():
                    continue

                chat_response = send_message_request(current_token, phone_number, message)
                
                if chat_response.status_code == 403:  # Token is not valid
                    current_token = await get_new_token()
                    chat_response = send_message_request(current_token, phone_number, message)

                if chat_response.status_code != 200:
                    logger.error(f"Failed to send message: {message}, Status Code: {chat_response.status_code}, Response: {chat_response.text}")
                    raise HTTPException(status_code=chat_response.status_code, detail=f"Failed to send message: {message}")

                logger.info(f"Message sent: {message}")
                messages_sent.append(message)
                
        except Exception as e:
            logger.exception(e)

    return {"status": "success", "messages_sent": messages_sent}

def get_token_from_sheet():
    sheet = service.spreadsheets().values().get(
        spreadsheetId=spreadsheet_id,
        range=f"{sheet_name}!{cell}"
    ).execute()
    return sheet.get('values', [[]])[0][0]

def update_token_in_sheet(token):
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"{sheet_name}!{cell}",
        valueInputOption="RAW",
        body={"values": [[token]]}
    ).execute()

async def get_new_token():
    url = "https://api.chatapp.online/v1/tokens"
    payload = {
        "email": "valentin@latoken.com",
        "password": "szxPx1TuHnJ7iR5YurYY",
        "appId": "app_43884_1"
    }
    response = requests.post(url, json=payload)
    if response.status_code == 200:
        token_data = response.json()
        new_token = token_data.get("data").get("accessToken")
        update_token_in_sheet(new_token)
        return new_token
    else:
        logger.error(f"Failed to get new token: {response.status_code}, Response: {response.text}")
        raise HTTPException(status_code=response.status_code, detail="Failed to get new token")

def send_message_request(token, phone_number, message):
    chat_api_url = f"https://api.chatapp.online/v1/licenses/48288/messengers/caWhatsApp/chats/{phone_number[1:]}/messages/text"
    headers = {
        "Authorization": token
    }
    body = {
        "text": message,
        "tracking": "botik",
        "sender": "system"
    }
    response = requests.post(chat_api_url, json=body, headers=headers)
    return response

def clean_phone_number(phone_number):
    return phone_number.replace('+', '').replace('(', '').replace(')', '').replace('-', '').replace(' ', '')

def send_message_sales_request(token, phone_number, template_id, template_params):
    cleaned_phone_number = clean_phone_number(phone_number)
    chat_api_url = f"https://api.chatapp.online/v1/licenses/48471/messengers/caWhatsApp/chats/{cleaned_phone_number}/messages/template"
    headers = {
        "Authorization": token,
        "Content-Type": "application/json"
    }
    body = {
        "template": {
            "id": template_id,
            "params": template_params
        },
        "tracking": "botik",
        "sender": "system"
    }
    response = requests.post(chat_api_url, json=body, headers=headers)
    return response

# def send_message_sales_request(token, phone_number, message):
#     chat_api_url = f"https://api.chatapp.online/v1/licenses/48471/messengers/caWhatsApp/chats/{phone_number[1:]}/messages/text"
#     headers = {
#         "Authorization": token
#     }
#     body = {
#         "text": message,
#         "tracking": "botik",
#         "sender": "system"
#     }
#     response = requests.post(chat_api_url, json=body, headers=headers)
#     return response

@spreadsheet.post("/send-message")
async def send_message(request: Request):
    body = await request.json()
    phone_number = body.get('phone_number')
    message = body.get('message')

    if not phone_number or not message:
        raise HTTPException(status_code=400, detail="Both phone_number and message are required")

    current_token = get_token_from_sheet()
    chat_response = send_message_request(current_token, phone_number, message)

    if chat_response.status_code == 403:  # Token is not valid
        current_token = await get_new_token()
        chat_response = send_message_request(current_token, phone_number, message)

    if chat_response.status_code != 200:
        logger.error(f"Failed to send message: {message}, Status Code: {chat_response.status_code}, Response: {chat_response.text}")
        raise HTTPException(status_code=chat_response.status_code, detail=f"Failed to send message: {message}")

    return {"status": "success", "message_sent": message}

@spreadsheet.post("/send-message-sales")
async def send_message_sales(request: Request):
    body = await request.json()
    phone_number = body.get('phone_number')
    template_id = body.get('template_id')
    template_params = body.get('template_params')

    if not phone_number or not template_id or not template_params:
        raise HTTPException(status_code=400, detail="phone_number, template_id and template_params are required")

    current_token = get_token_from_sheet()
    chat_response = send_message_sales_request(current_token, phone_number, template_id, template_params)

    if chat_response.status_code == 403:  # Token is not valid
        current_token = await get_new_token()
        chat_response = send_message_sales_request(current_token, phone_number, template_id, template_params)

    if chat_response.status_code != 200:
        logger.error(f"Failed to send message: {template_params}, Status Code: {chat_response.status_code}, Response: {chat_response.text}")
        raise HTTPException(status_code=chat_response.status_code, detail=f"Failed to send message: {template_params}")

    return {"status": "success", "message_sent": template_params}

BASE_URL = "https://latokenteam.amocrm.ru/api/v4/"

@spreadsheet.get("/process-contact/{contact_name}")
async def process_contact(contact_name: str):
    import httpx
    
    async with httpx.AsyncClient() as client:
        client.headers.update({"Authorization": f"Bearer {config.AMOCRM_TOKEN_SALES}"})
        
        result = await find_contact_and_leads_by_name(client, contact_name)
        if not result["contact_id"]:
            raise HTTPException(status_code=404, detail="Contact not found")
        
        lead = await find_lead(client, contact_name)
        if not lead:
            raise HTTPException(status_code=404, detail="Lead not found")
        
        await add_contact_to_lead(client, lead["id"], result["contact_id"])
        
        return {
            "contact_id": result["contact_id"],
            "lead_id": lead["id"],
            "lead_name": contact_name
        }

async def find_contact_and_leads_by_name(client, name: str):
    contact_url = f"{BASE_URL}contacts?query={name}"
    contact_response = await client.get(contact_url)
    contact_id = None
    lead_ids = []
    
    if contact_response.status_code == 200:
        contact_result = contact_response.json()
        contact = next((c for c in contact_result["_embedded"]["contacts"] if c["name"] == name), None)
        if contact:
            contact_id = contact["id"]
            lead_ids = await find_lead_ids(client, contact_id)
    
    return {"contact_id": contact_id, "lead_ids": lead_ids}

async def find_lead_ids(client, contact_id: str):
    links_url = f"{BASE_URL}contacts/{contact_id}/links"
    links_response = await client.get(links_url)
    if links_response.status_code == 200:
        links_result = links_response.json()
        leads_links = [link["to_entity_id"] for link in links_result["_embedded"]["links"] if link["to_entity_type"] == "leads"]
        return leads_links
    return []

async def find_lead(client, name: str, filter: str = "&filter[name]="):
    from urllib.parse import quote
    lead_url = f"{BASE_URL}leads?filter[pipeline_id]=1289332" + filter + quote(replace_contact_name(name))
    lead_response = await client.get(lead_url)
    if lead_response.status == 200:
            lead_result = await lead_response.text()
            if not lead_result:
                cf_filter = "&filter[custom_fields_values][809266][equals]="
                if filter == cf_filter:
                    return None
                return await find_lead(client, name, cf_filter)

            lead_json = json.loads(lead_result)
            if lead_json["_embedded"]["leads"]:
                return lead_json["_embedded"]["leads"][0]
    else:
        print(f"Error retrieving lead: {lead_response.status}")

    return None

async def add_contact_to_lead(client, lead_id: str, contact_id: str):
    url = f"{BASE_URL}leads/{lead_id}/link"
    data = [{"to_entity_id": int(contact_id), "to_entity_type": "contacts"}]
    response = await client.post(url, json=data)
    logger.info('response' + str(response.status_code)  + str(response.json()))
    if response.status_code != 200:
        raise HTTPException(status_code=response.status_code, detail=f"Error adding contact to lead: {response.text}")

def replace_contact_name(contact_name: str):
    import re
    pattern = r"(.+ \(.+\) .+) x LATOKEN"
    if re.match(pattern, contact_name):
        return re.sub(pattern, r"\1", contact_name)
    return None

def get_templates_request(token):
    url = "https://api.chatapp.online/v1/licenses/48471/messengers/caWhatsApp/templates"
    headers = {
        "Authorization": f"{token}",
        "Content-Type": "application/json"
    }
    response = requests.get(url, headers=headers)
    return response

@spreadsheet.get("/get_templates_waba")
async def get_templates_waba():
    current_token = get_token_from_sheet()
    logger.info(f"Current token: {current_token}")
    templates_response = get_templates_request(current_token)

    if templates_response.status_code == 403:  # Token is not valid
        current_token = await get_new_token()
        logger.info(current_token)
        templates_response = get_templates_request(current_token)

    if templates_response.status_code != 200:
        raise HTTPException(status_code=templates_response.status_code, detail=templates_response.text)

    return {"status": "success", "response": templates_response.json()}