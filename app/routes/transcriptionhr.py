from urllib.parse import parse_qs
import aiohttp
import asyncio
import json
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import re
from fastapi import APIRouter, Request, Query, HTTPException
import requests
import threading
import io
import gspread
from typing import Annotated

from routes.analyze import (
    punctuation_assistant, 
    call_status, 
    analyze_hr, 
    fetch_pdf_from_url, 
    pdf_to_text, 
    recognize_speech,
    create_list_questions
)
import config

from pydantic import BaseModel, ValidationError, Field
from loguru import logger
import time
from datetime import datetime

from pydub import AudioSegment



transcriptionhr = APIRouter()

class EmbeddedLeads:
    def __init__(self, leads):
        self.leads = leads

class AmoCRMResponseContact:
    def __init__(self, embedded, links):
        self.embedded = embedded
        self.links = links


class WebhookData(BaseModel):
    domain: str
    event: str
    direction: str
    uuid: str
    origin: str
    caller: str
    callee: str
    from_domain: str
    to_domain: str
    gateway: str
    date: int
    call_duration: int
    dialog_duration: int
    hangup_cause: str
    download_url: str
    quality_score: float


def get_json_vacancy():
    import gspread
    gc = gspread.service_account(filename="valentinwm-tg-36da0854f6c0.json")
    gs = gc.open_by_url(
        "https://docs.google.com/spreadsheets/d/19FbsRnpgitFa_opHy_oTIb_-9EIFERKTohkD3oS9u9A/edit#gid=0"
    )
    sheet = gs.get_worksheet("Variables")
    json_vacancy = sheet.cell(4, 1).value
    return json_vacancy



def get_url_data_from_crm(lead_id):
    url = f"https://hrlatoken.amocrm.com/api/v4/leads/{lead_id}"
    headers = {
                    "Authorization": f"Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsImp0aSI6IjY4MTc0OWY3YzIyYzZkZGQ1YTRkMzk5MTY1NGVjNTEwN2QzMTM2NzFkYzk5MjlkMDc2YzcwNjQ0ZTlhYjc1ZWE5YjM5OTljYWM5NDM3YWIzIn0.eyJhdWQiOiJkNDVlODdhZS1mMDNlLTQ1YzItOGZiZC02Mzg4MDNlNjBlZGUiLCJqdGkiOiI2ODE3NDlmN2MyMmM2ZGRkNWE0ZDM5OTE2NTRlYzUxMDdkMzEzNjcxZGM5OTI5ZDA3NmM3MDY0NGU5YWI3NWVhOWIzOTk5Y2FjOTQzN2FiMyIsImlhdCI6MTcxNDQ4NzEyOSwibmJmIjoxNzE0NDg3MTI5LCJleHAiOjE4MzI4ODk2MDAsInN1YiI6IjM4MTY2NjQiLCJncmFudF90eXBlIjoiIiwiYWNjb3VudF9pZCI6Mjg2NTI3MDcsImJhc2VfZG9tYWluIjoia29tbW8uY29tIiwidmVyc2lvbiI6Miwic2NvcGVzIjpbImNybSIsImZpbGVzIiwiZmlsZXNfZGVsZXRlIiwibm90aWZpY2F0aW9ucyIsInB1c2hfbm90aWZpY2F0aW9ucyJdLCJoYXNoX3V1aWQiOiI1NmQ1ZWQ1Yi1hNTY3LTQyYTAtODY5My0wODQ4ZDBkMWVhMjYifQ.MKf3IW9PDkXWAQAkOPs0ux_4DQKzKntpYyV9O0BwZX-GGcSMxaLrifkn2lRobIkO9rqkP0OhsTk5-IXToDGwdT_k8G8ma3ZWtIvdhdCiVpZeuQamjHQ7xa-3LdzT43c0CIvMcDjleKfdMNbLjeKaXIMJxG2UCsc2Nw7AsQ-p9O1GZ3LiqLycEe6FH7oyCxTe1Qq8o2z0r_jx4iABl7t2RDjIsjR4fx_YvK0u5ZXI7cyWL-clzwAnRHuik1cc_4ud-1_uAbJx8HNU4OJqxCugjYRgTlY1_O4oYnnaSP66SdN3Le9RFcPhkI_0OxdLHV3YGhKJG8FdflquIQk-GWKudw"
    }

    # Выполнение синхронного HTTP-запроса
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        raise Exception("Error retrieving contacts")
    
    response_json = response.json()
    return response_json


class ContactManager:
    def __init__(self):
        self._is_getting_contacts = False
        self._lock = asyncio.Lock()

    async def get_contacts_async(self, page):
        url = f"https://hrlatoken.amocrm.com/api/v4/leads?page={page}&limit=250"
        headers = {
                        "Authorization": f"Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsImp0aSI6IjY4MTc0OWY3YzIyYzZkZGQ1YTRkMzk5MTY1NGVjNTEwN2QzMTM2NzFkYzk5MjlkMDc2YzcwNjQ0ZTlhYjc1ZWE5YjM5OTljYWM5NDM3YWIzIn0.eyJhdWQiOiJkNDVlODdhZS1mMDNlLTQ1YzItOGZiZC02Mzg4MDNlNjBlZGUiLCJqdGkiOiI2ODE3NDlmN2MyMmM2ZGRkNWE0ZDM5OTE2NTRlYzUxMDdkMzEzNjcxZGM5OTI5ZDA3NmM3MDY0NGU5YWI3NWVhOWIzOTk5Y2FjOTQzN2FiMyIsImlhdCI6MTcxNDQ4NzEyOSwibmJmIjoxNzE0NDg3MTI5LCJleHAiOjE4MzI4ODk2MDAsInN1YiI6IjM4MTY2NjQiLCJncmFudF90eXBlIjoiIiwiYWNjb3VudF9pZCI6Mjg2NTI3MDcsImJhc2VfZG9tYWluIjoia29tbW8uY29tIiwidmVyc2lvbiI6Miwic2NvcGVzIjpbImNybSIsImZpbGVzIiwiZmlsZXNfZGVsZXRlIiwibm90aWZpY2F0aW9ucyIsInB1c2hfbm90aWZpY2F0aW9ucyJdLCJoYXNoX3V1aWQiOiI1NmQ1ZWQ1Yi1hNTY3LTQyYTAtODY5My0wODQ4ZDBkMWVhMjYifQ.MKf3IW9PDkXWAQAkOPs0ux_4DQKzKntpYyV9O0BwZX-GGcSMxaLrifkn2lRobIkO9rqkP0OhsTk5-IXToDGwdT_k8G8ma3ZWtIvdhdCiVpZeuQamjHQ7xa-3LdzT43c0CIvMcDjleKfdMNbLjeKaXIMJxG2UCsc2Nw7AsQ-p9O1GZ3LiqLycEe6FH7oyCxTe1Qq8o2z0r_jx4iABl7t2RDjIsjR4fx_YvK0u5ZXI7cyWL-clzwAnRHuik1cc_4ud-1_uAbJx8HNU4OJqxCugjYRgTlY1_O4oYnnaSP66SdN3Le9RFcPhkI_0OxdLHV3YGhKJG8FdflquIQk-GWKudw"

        }
        
        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers) as response:
                if response.status != 200:
                    raise Exception("Error retrieving contacts")
                response_json = await response.json()
                embedded = EmbeddedLeads(response_json.get('_embedded', {}).get('leads', []))
                links = response_json.get('_links', {})
                return AmoCRMResponseContact(embedded, links)


    async def get_all_contacts_async(self):
        async with self._lock:
            if self._is_getting_contacts:
                logger.info("Google Sheet already updating")
                return
            self._is_getting_contacts = True

        try:
            page = 1
            more_pages = True
            row = 2
            gc = gspread.service_account(filename="./valentinwm-tg-36da0854f6c0.json")
            gs = gc.open_by_url(
                    "https://docs.google.com/spreadsheets/d/19FbsRnpgitFa_opHy_oTIb_-9EIFERKTohkD3oS9u9A/edit#gid=0"
                )
            sheet = gs.get_worksheet("Leads amoCRM")
            start_row = 2
            while more_pages:
                to_cell = []
                logger.info(f"Началось получение контактов {page}")
                
                response = await self.get_contacts_async(page)
                logger.info(f"Закончилось получение контактов {page}")
                
                if response.embedded.leads is None:
                    raise Exception("Error retrieving contacts or no contacts found.")
                for i in range(len(response.embedded.leads)):
                    phone = None
                    email = None
                    if response.embedded.leads[i]['custom_fields_values'] is not None:
                        cell_list = []
                        time_create = int(response.embedded.leads[i]['created_at'])
                        for lead in response.embedded.leads[i]['custom_fields_values']:
                            
                            if lead['field_id'] == 135229:
                                phone = lead['values'][0]['value']
                            elif lead['field_id'] == 135213:
                                email = lead['values'][0]['value']
                            id = response.embedded.leads[i]['id']

                        if phone is not None:
                            matches = re.findall(r'\+?\d{1,3}?[\s-]?\(?\d{1,5}?\)?[\s-]?\d[\d\s()-]*\d', phone)

                            phone_numbers = [''.join(re.findall(r'\d', match)) for match in matches]
                            if len(phone_numbers) == 1:
                                if (phone_numbers[0] != '') and (time_create > 1672531200):
                                    to_cell.append([id, str(phone_numbers[0]), email])
                            
                            if len(phone_numbers) >= 2:
                                if phone_numbers[0] == phone_numbers[1]:
                                    to_cell.append([id, str(phone_numbers[0]), email])
                                else:
                                    for phon in phone_numbers:
                                        if phon != '' and (time_create > 1672531200):
                                            to_cell.append([id, phon, email])
                end_row = start_row + len(to_cell) 
                range_to_update = f'A{start_row}:D{end_row}'
                sheet.update(range_to_update, to_cell)
                start_row += len(to_cell)

                if response.links.get('next', {}).get('href'):
                    page += 1
                else:
                    more_pages = False
            logger.info("Google Sheet обновлен")
        finally:
            async with self._lock:
                self._is_getting_contacts = False

contact_manager = ContactManager()
            


def get_lead_id_by_phone(phone_number, phone_numbers, sheet):
    def clean_phone_number(phone):
        return ''.join(char for char in phone if char.isdigit())

    cleaned_phone_number = clean_phone_number(phone_number)
    for i, phone in enumerate(phone_numbers):
        if clean_phone_number(phone) == cleaned_phone_number:
            lead_url = sheet.cell(i + 1, 1).value
            logger.info("Phone: " + phone)
            logger.info('Lead Id: https://hrlatoken.amocrm.com/leads/detail/' + lead_url)

            lead_id = lead_url.split("/")[-1]
            data_crm = get_url_data_from_crm(lead_id)
            return lead_id, data_crm
    return None, None

def get_lead_id_by_phone_hackathon(phone_number, phone_numbers, sheet):
    def clean_phone_number(phone):
            return ''.join(char for char in phone if char.isdigit())
    cleaned_phone_number = clean_phone_number(phone_number)
    for i, phone in enumerate(phone_numbers):
        if clean_phone_number(phone) == cleaned_phone_number:
            lead_url = sheet.cell(i + 1, 54).value
            logger.info("Phone: " + phone)
            logger.info('Lead Id: ' + lead_url)

            lead_id = lead_url.split("/")[-1]
            data_crm = get_url_data_from_crm(lead_id)
            return lead_id, data_crm
    return None, None



@transcriptionhr.post("/webhooktranscribationhr")
async def receive_webhook(request: Request):
    form = await request.form()

    # Преобразование QueryParams в словарь
    datadict = {key: form[key] for key in form}

    # Преобразуем строковые значения в нужные типы
    datadict['date'] = int(datadict.get('date', 0))
    if 'call_duration' in datadict:
        datadict['call_duration'] = int(datadict['call_duration'])
    if 'dialog_duration' in datadict:
        datadict['dialog_duration'] = int(datadict['dialog_duration'])
    if 'quality_score' in datadict:
        datadict['quality_score'] = int(datadict['quality_score'])

    data = WebhookData(**datadict)

    import io
    import gspread
    gc = gspread.service_account(filename="valentinwm-tg-36da0854f6c0.json")
    gs = gc.open_by_url(
        "https://docs.google.com/spreadsheets/d/19FbsRnpgitFa_opHy_oTIb_-9EIFERKTohkD3oS9u9A/edit#gid=0"
    )
    sheet = gs.get_worksheet("Leads amoCRM")
    phone_numbers = sheet.col_values(2)

    # Загрузка файла по URL
    download_url = data.download_url
    phone_number = data.callee
    response = requests.get(download_url)

    if download_url.endswith('.mp3'):
        url_vacancy, url_resume = None, None
        try:        
            lead_id, data_crm = get_lead_id_by_phone(phone_number, phone_numbers, sheet)
            url_for_crm_bar = f"https://hrlatoken.amocrm.com/api/v4/leads/{lead_id}"

            # Проверка, если данные найдены
            if lead_id and data_crm:
                for lead_data in data_crm['custom_fields_values']:
                    if lead_data['field_id'] == 824368:
                        url_resume = lead_data['values'][0]['value']
                    if lead_data['field_id'] == 874205:
                        url_vacancy = lead_data['values'][0]['value']
            else:
                for _ in range(1):  # попробуем перезагрузить данные один раз
                    asyncio.create_task(contact_manager.get_all_contacts_async())
                gc = gspread.service_account(filename="valentinwm-tg-36da0854f6c0.json")
                gs = gc.open_by_url(
                    "https://docs.google.com/spreadsheets/d/19FbsRnpgitFa_opHy_oTIb_-9EIFERKTohkD3oS9u9A/edit#gid=0"
                )
                sheet = gs.get_worksheet(0)
                phone_numbers = sheet.col_values(7)

                lead_id, data_crm = get_lead_id_by_phone_hackathon(phone_number, phone_numbers, sheet)
                if lead_id and data_crm:
                        # Если данные найдены после перезагрузки
                        for lead_data in data_crm['custom_fields_values']:
                            if lead_data['field_id'] == 824368:
                                url_resume = lead_data['values'][0]['value']
                            if lead_data['field_id'] == 874205:
                                url_vacancy = lead_data['values'][0]['value']
        except Exception as e:
            logger.info("Phone Not Found")
            return {"status": "processed"}            

        buffer = io.BytesIO(response.content)
        buffer.seek(0)
        try:
            audio = AudioSegment.from_file(buffer)
            audio_length = len(audio)
            audio_fragments = []

            # Разбиваем аудио на фрагменты по минутам
            for start_time in range(0, audio_length, 60 * 1000):
                end_time = start_time + 60 * 1000
                fragment = audio[start_time:end_time]
                buffer = io.BytesIO()
                fragment.export(buffer, format="mp3")
                buffer.seek(0)
                audio_fragments.append(buffer)

            transcription_message = ""
            for i, fragment_buffer in enumerate(audio_fragments):
                message = recognize_speech(fragment_buffer)
                transcription_message += message

        except Exception as e:
            logger.error(e)
            transcription_message = "Неразборчиво или пустой диалог"
        #logger.info(transcription)
        call_state = call_status(transcription_message)
        logger.info("call_status: " + call_state)


        call_date = datetime.today().strftime("%m/%d/%Y")
        logger.info("Call Date: " + call_date)

        if call_state == "Не ответил":
            headers_for_crm = {
                "Authorization": f'Bearer {config.AMOCRM_TOKEN_HR}',
                "Content-Type": "application/json"
            }
            data_call = {
    "custom_fields_values": [
    {
        "field_id": 874447,
        "field_name": "Call Status",
        "field_type": "select",
        "values": [
            {"value": call_state}
        ]
    },
    {
        "field_id": 874449,
        "field_name": "Call Date",
        "field_type": "date",
        "values": [
            {"value": int(time.time())}
        ]
    }
    ]
            }
    



            response = requests.patch(url=url_for_crm_bar,json=data_call, headers=headers_for_crm)
            if response.status_code in range(200, 299):
                logger.info("Лид успешно обновлен.")
            else:
                logger.info(f"Ошибка при обновлении лида: {response.status_code}")

            return {"status": "processed"}
        if call_state == "Ответил":
            headers_for_crm = {
                "Authorization": f'Bearer {config.AMOCRM_TOKEN_HR}',
                "Content-Type": "application/json"
            }
            data_call = {
    "custom_fields_values": [
    {
        "field_id": 874447,
        "field_name": "Call Status",
        "field_type": "select",
        "values": [
            {"value": call_state}
        ]
    },
    {
        "field_id": 874449,
        "field_name": "Call Date",
        "field_type": "date",
        "values": [
            {"value": int(time.time())}
        ]
    }
    ]
            }
    



            response = requests.patch(url=url_for_crm_bar,json=data_call, headers=headers_for_crm)
            if response.status_code in range(200, 299):
                logger.info("Лид успешно обновлен.")
            else:
                logger.info(f"Ошибка при обновлении лида: {response.status_code}")
                print(response.json)
            
        transcription_message = punctuation_assistant(str(transcription_message))[8:-3]
        transcription_message = json.loads(transcription_message)
        vacancies = json.loads(get_json_vacancy())
        vacancy_url = re.sub(r'\s?\(Удаленно\)\s?|\s?\(удаленно\)\s?', '', url_vacancy)
        try:
            js_vacancy  = vacancies[vacancy_url][0]
        except:
            js_vacancy  = vacancies["Разработчик операций AI, Python/React  для меняющих профессию на разработчика"][0]
            logger.info("Not Found Vacancy " + vacancy_url)

        try:
            logger.info("Starting Analyze")
            result_analyze_hr = analyze_hr(str(transcription_message), pdf_to_text(fetch_pdf_from_url(url_resume)),
                                           js_vacancy)
        except Exception as e:
            result_analyze_hr = 'Неразборчиво или пустой диалог'
        result_analyze_hr = json.loads(result_analyze_hr)
        logger.info(result_analyze_hr.keys())
        url_for_crm = f"https://hrlatoken.amocrm.com/api/v4/leads/{lead_id}/notes"
        url_for_crm_bar = f"https://hrlatoken.amocrm.com/api/v4/leads/{lead_id}"

        headers_for_crm = {
                "Authorization": f'Bearer {config.AMOCRM_TOKEN_HR}',
                "Content-Type": "application/json"
            }
        body_for_crm = [{
                "entity_id": lead_id,
                "note_type": "common",
                "params": {
                    "text": "\n".join([message['role'] + ' ' + message['message'] for message in transcription_message])
                }
            },
                {
                    "entity_id": lead_id,
                    "note_type": "common",
                    "params": {
                        "text":"Кратко: " + str(result_analyze_hr["HR_brief"]) + " \n" +"HR Score: " + str(result_analyze_hr["HR_score"]) +"\n\n\nВесь анализ: " + str(result_analyze_hr["HR_analyze"]) + "\nИсправленный Диалог:" + str(result_analyze_hr['HR_dialogue'])
                    }
                },
            ]
        add_to_lead = requests.post(url=url_for_crm, json=body_for_crm, headers=headers_for_crm)
        logger.info(add_to_lead)
        headers_for_crm = {
                "Authorization": f'Bearer {config.AMOCRM_TOKEN_HR}',
                "Content-Type": "application/json"
            }
        data_call = {
    "custom_fields_values": [
    {
        "field_id": 874525,
        "field_name": "Call Score",
        "field_type": "numeric",
        "values": [
            {"value": str(result_analyze_hr["HR_score"])}
        ]
    }
    ]
            }
    



        response = requests.patch(url=url_for_crm_bar,json=data_call, headers=headers_for_crm)
        if response.status_code in range(200, 299):
                logger.info("Лид успешно обновлен.")
        else:
                logger.info(f"Ошибка при обновлении лида: {response.status_code}")
                print(response.json)


    return {"status": "processed"}


@transcriptionhr.post('/submit_phone')
async def create_questions(request: Request):
    body_bytes = await request.body()
    body_str = body_bytes.decode('utf-8')
    body_dict = parse_qs(body_str)
    phone_number_str = body_dict.get('phone_number', [''])[0]
    phone_number_str = ''.join(char for char in phone_number_str if char.isdigit())
    
    if not phone_number_str:
        raise HTTPException(status_code=400, detail="phone_number is required")
    
    # Дополнительная логика здесь
    import io
    import gspread
    gc = gspread.service_account(filename="valentinwm-tg-36da0854f6c0.json")
    gs = gc.open_by_url(
        "https://docs.google.com/spreadsheets/d/19FbsRnpgitFa_opHy_oTIb_-9EIFERKTohkD3oS9u9A/edit#gid=0"
    )
    sheet = gs.get_worksheet("Leads amoCRM")
    phone_numbers = sheet.col_values(2)
    lead_id, data_crm = None, None
    try:        
        lead_id, data_crm = get_lead_id_by_phone(phone_number_str, phone_numbers, sheet)   
        if lead_id and data_crm:
            for lead_data in data_crm['custom_fields_values']:
                if lead_data['field_id'] == 824368:
                        url_resume = lead_data['values'][0]['value']
                if lead_data['field_id'] == 874205:
                        url_vacancy = lead_data['values'][0]['value']
        else:
            logger.info("Upload DB")
            for _ in range(1):  # попробуем перезагрузить данные один раз
                asyncio.create_task(contact_manager.get_all_contacts_async())
            gc = gspread.service_account(filename="valentinwm-tg-36da0854f6c0.json")
            gs = gc.open_by_url(
                    "https://docs.google.com/spreadsheets/d/19FbsRnpgitFa_opHy_oTIb_-9EIFERKTohkD3oS9u9A/edit#gid=0"
                )
            sheet = gs.get_worksheet(0)
            phone_numbers = sheet.col_values(7)
            lead_id, data_crm = get_lead_id_by_phone_hackathon(phone_number_str, phone_numbers, sheet)
            if lead_id and data_crm:
                    # Если данные найдены после перезагрузки
                    for lead_data in data_crm['custom_fields_values']:
                        if lead_data['field_id'] == 824368:
                            url_resume = lead_data['values'][0]['value']
                        if lead_data['field_id'] == 874205:
                            url_vacancy = lead_data['values'][0]['value']
                        
    except:
        logger.info("submit_phone Phone Not Found")
        return {"status": "processed"}
    vacancies = json.loads(get_json_vacancy())
    vacancy_url = re.sub(r'\s?\(Удаленно\)\s?|\s?\(удаленно\)\s?', '', url_vacancy)
    try:
            js_vacancy  = vacancies[vacancy_url][0]
    except:
            logger.info("Not Found Vacancy " + vacancy_url)
            js_vacancy  = vacancies["Разработчик операций AI, Python/React  для меняющих профессию на разработчика"][0]

    list_questions = create_list_questions(resume=pdf_to_text(fetch_pdf_from_url(url_resume)), name_vacancy=vacancy_url, vacancy=js_vacancy)
    url_for_crm = f"https://hrlatoken.amocrm.com/api/v4/leads/{lead_id}/notes"
    headers_for_crm = {
                "Authorization": f'Bearer {config.AMOCRM_TOKEN_HR}',
                "Content-Type": "application/json"
            }
    body_for_crm = [{
                "entity_id": lead_id,
                "note_type": "common",
                "params": {
                    "text": list_questions
                }
            },
            ]
    add_to_lead = requests.post(url=url_for_crm, json=body_for_crm, headers=headers_for_crm)
    logger.info(add_to_lead)
    return{"status": "processed"}