from fastapi import APIRouter, Request
from pydantic import BaseModel
import requests
import config
from loguru import logger
import io
from pydub import AudioSegment
from datetime import datetime
from sales.assistant import recognize_speech, punctuation_assistant, call_status
import time
import json


transcriptionsales = APIRouter()

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

@transcriptionsales.post("/webhooktranscribationsales")
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
    download_url = data.download_url
    phone_number = data.callee
    response_pbx = requests.get(download_url)

    if download_url.endswith('.mp3'):
        phone_number = ''.join(char for char in phone_number if char.isdigit())
        try:
            headers = {
        'Authorization': f'Bearer {config.AMOCRM_TOKEN_SALES}',
        'Content-Type': 'application/json'
            }
            params = {
                'query': phone_number
                    }
            response = requests.get(f'https://latokenteam.amocrm.ru/api/v4/leads', headers=headers, params=params)
            data = response.json()
        except:
            logger.info("Phone Not Found")
            return {"status": "processed"}  
        lead_id = data['_embedded']['leads'][0]['id']
        logger.info('https://latokenteam.amocrm.ru/leads/detail/' + str(lead_id))
        url_for_crm_bar = f"https://latokenteam.amocrm.ru/api/v4/leads/{lead_id}"
        buffer = io.BytesIO(response_pbx.content)
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

        call_state = call_status(transcription_message)
        call_date = datetime.today().strftime("%m/%d/%Y")
        logger.info("Call Date: " + call_date)
        if call_state == "Not answered":
            headers = {
        'Authorization': f'Bearer {config.AMOCRM_TOKEN_SALES}',
        'Content-Type': 'application/json'
            }
            data_call = {
            "custom_fields_values": [
            {
                "field_id": 809258,
                "field_name": "Call Status",
                "field_type": "select",
                "values": [
                    {"value": call_state}
                ]
            },
            {
                "field_id": 809262, 
                "field_name": "Call Date",
                "field_type": "date",
                "values": [
                    {"value": int(time.time())}
                ]
            }
            ]
                    }
            



            response = requests.patch(url=url_for_crm_bar,json=data_call, headers=headers)
            logger.debug(response)
            if response.status_code in range(200, 299):
                logger.info("Лид успешно обновлен.")
            else:
                logger.info(f"Ошибка при обновлении лида: {response.status_code}")

                return {"status": "processed"}
        if call_state == "Answered":
            headers = {
        'Authorization': f'Bearer {config.AMOCRM_TOKEN_SALES}',
        'Content-Type': 'application/json'
            }
            data_call = {
            "custom_fields_values": [
            {
                "field_id": 809258,
                "field_name": "Call Status",
                "field_type": "select",
                "values": [
                    {"value": call_state}
                ]
            },
            {
                "field_id": 809262,
                "field_name": "Call Date",
                "field_type": "date",
                "values": [
                    {"value": int(time.time())}
                ]
            }
            ]
                    }   
                
    



            response = requests.patch(url=url_for_crm_bar,json=data_call, headers=headers)
            if response.status_code in range(200, 299):
                    logger.info("Лид успешно обновлен.")
            else:
                logger.info(f"Ошибка при обновлении лида: {response.status_code}")
        print(response.json)    
        transcription_message = json.loads(punctuation_assistant(str(transcription_message)))
        url_for_crm = f"https://latokenteam.amocrm.ru/api/v4/leads/{lead_id}/notes"
        headers = {
        'Authorization': f'Bearer {config.AMOCRM_TOKEN_SALES}',
        'Content-Type': 'application/json'
            }
        body_for_crm = [{
                "entity_id": str(lead_id),
                "note_type": "common",
                "params": {
                    "text": "\n".join([message['role'] + ' ' + message['message'] for message in transcription_message['dialogue']])
                }
            }]
        
        add_to_lead = requests.post(url=url_for_crm, json=body_for_crm, headers=headers)
        logger.info(add_to_lead)
    return {"status": "processed"}
