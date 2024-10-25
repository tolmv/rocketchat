import json
from routes.spreadsheet import ScoringData, scoring
import config
import gspread
import requests as req
import httpx
from typing import List

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.contacts import ImportContactsRequest, DeleteContactsRequest
from telethon.tl.types import InputPhoneContact, InputUser

from utils.upload_pdf import append_data_to_sheet, upload_file_from_resume, update_cell

from loguru import logger

employer_id = "2870783"
manager_id = "13685947"
URL = "https://api.hh.ru/"
SHEET_URL = config.SHEET_KEY

gc = gspread.service_account(filename="valentinwm-tg-36da0854f6c0.json")
gs = gc.open_by_url(
    "https://docs.google.com/spreadsheets/d/19FbsRnpgitFa_opHy_oTIb_-9EIFERKTohkD3oS9u9A/edit#gid=0"
)

class HHUnauthorizedError(Exception):
    """Ошибка для HTTP 401 (Unauthorized)."""
    def __init__(self, message="Неавторизованный доступ", error_code=401):
        super().__init__(message)
        self.error_code = error_code

def go_refresh_token():
    grant_type = 'refresh_token'

    # The token endpoint for the hh.ru API
    token_url = 'https://api.hh.ru/token'

    # The payload to be sent to the token endpoint
    payload = {
        'refresh_token': config.HH_REFRESH_TOKEN,
        'grant_type': grant_type
    }

    # Sending the POST request to the token endpoint
    response = req.post(token_url, data=payload)

    # Handling the response
    if response.status_code == 200:
        token_data = response.json()
        logger.info(f"token refresh attempt {token_data}")
        ws = gs.get_worksheet_by_id(1224148811)
        config.HH_TOKEN = token_data['access_token']
        config.HH_REFRESH_TOKEN = token_data['refresh_token']
        ws.update_cell(2, 1, token_data['access_token'])
        ws.update_cell(2, 2, token_data['refresh_token'])
        # token_data = {
        #     'access_token' : config.HH_TOKEN,
        #     'refresh_token' : config.HH_REFRESH_TOKEN
        # }
        # with open('tokens.json', 'w') as file:
        #     json.dump(token_data, file)
    else:
        logger.info(f"token was not refreshed {response.status_code} {response.text} ")

def go_get_tokens():
    try:
        ws = gs.get_worksheet_by_id(1224148811)
        access_tk = ws.cell(2, 1).value
        refresh_tk = ws.cell(2, 2).value
        config.HH_TOKEN = access_tk
        config.HH_REFRESH_TOKEN = refresh_tk
        logger.info(f"TOKENS {access_tk} {refresh_tk}")
    except Exception as e:
        logger.error(f"TOKENS ERROR {e}")

go_get_tokens()

def using_hh_token(func):
    def checker(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except HHUnauthorizedError:
            go_refresh_token()
            return func(*args, **kwargs)
    return checker


@using_hh_token
def make_request_hh(url, method='GET', headers=None, params=None, data=None, json=None):
    """
    Делает HTTP-запрос и возвращает ответ.

    :param url: URL для запроса.
    :param method: HTTP-метод (например, 'GET', 'POST', 'PUT', 'DELETE').
    :param headers: Словарь с заголовками запроса.
    :param params: Словарь с параметрами строки запроса.
    :param data: Словарь с данными для отправки в теле запроса (для 'POST', 'PUT').
    :param json: JSON для отправки в теле запроса (для 'POST', 'PUT').
    :return: Ответ от сервера (объект Response).
    """
    response = req.request(
        method=method,
        url=url,
        headers=headers,
        params=params,
        data=data,
        json=json
    )
    if response.status_code == 403 or response.status_code == 401:
        raise HHUnauthorizedError()
    return response

def async_using_hh_token(func):
    async def checker(*args, **kwargs):
        try:
            return await func(*args, **kwargs)
        except HHUnauthorizedError:
            go_refresh_token()
            return await func(*args, **kwargs)
    return checker

@async_using_hh_token
async def async_request_hh(session: httpx.AsyncClient, url: str, method: str = "GET", **kwargs):
    response = await session.request(method, url, **kwargs)
    if response.status_code == 401 or response.status_code == 403:
        raise HHUnauthorizedError()
    return response


def get_managers(employer_id: str) -> List[str]:
    """Получает список ID всех менеджеров работодателя."""

    res = make_request_hh(f"https://api.hh.ru/employers/{employer_id}/managers", headers = {
        "Authorization": f"Bearer {config.HH_TOKEN}",
        "User-Agent": "HH-User-Agent"
    })
    data = res.json()
    
    return [manager['id'] for manager in data['items']]


def get_active_vacancies():
    manager_ids = get_managers(employer_id)
    vacancies = []

    for manager_id in manager_ids:
        page = 0
        has_more = True
        while has_more: 
            res = make_request_hh(
                f"https://api.hh.ru/employers/{employer_id}/vacancies/active",
                params={"manager_id": manager_id, "page": page, "per_page": 50},
                headers={"Authorization": f"Bearer {config.HH_TOKEN}", "User-Agent": "HH-User-Agent"},
            )
            data = res.json()

            if "items" not in data or "pages" not in data:
                logger.info('skip ' + page + ' ' + manager_id)
                continue

            vacancies += data["items"]
            has_more = data["pages"] > page + 1
            page += 1

    return vacancies


def get_negotiations(vacancy_id, start_date):
    res = make_request_hh(
        "https://api.hh.ru/negotiations",
        headers={"Authorization": f"Bearer {config.HH_TOKEN}", "User-Agent": "HH-User-Agent"},
        params={
            "vacancy_id": vacancy_id,
            "with_generated_collections": "true",
            "order_by": "created_at",
            "page": 1,
            "status": "all",
        },
    ).json()
    negotiations = []

    for collection in res["collections"]:
        url = collection["url"].split("?")[0]
        page = 0
        while True:
            page += 1
            res = make_request_hh(
                url,
                headers={
                    "Authorization": f"Bearer {config.HH_TOKEN}",
                    "User-Agent": "HH-User-Agent",
                },
                params={
                    "vacancy_id": vacancy_id,
                    "order_by": "created_at",
                    "order": "desc",
                    "page": page,
                    "status": "all",
                },
            )

            if(not res.json()["items"]): 
                break

            new_negotiations = res.json()["items"]

            # if (
            #     new_negotiations[-1]["created_at"] < start_date
            # ):
            #     continue

            negotiations += new_negotiations

    return negotiations




def get_me():
    res = make_request_hh(
        "https://api.hh.ru/me",
        headers={"Authorization": f"Bearer {config.HH_TOKEN}", "User-Agent": "HH-User-Agent"},
    )
    return res.json()

def get_contacts(resume_id):
    contacts = {}
    comments = []
    res = make_request_hh(
        f"https://api.hh.ru/resumes/{resume_id}",
        headers={"Authorization": f"Bearer {config.HH_TOKEN}", "User-Agent": "HH-User-Agent"},
    ).json()

    for contact in res["contact"]:
        try:
            contact_type = contact["type"]["id"]
            if contact["type"]["id"] == "cell":
                contacts[contact_type] = f"'{contact['value']['formatted']}"
            elif contact["type"]["id"] == "email":
                contacts[contact_type] = contact["value"]

            if contact.get("comment"):
                comments.append(contact["comment"])
        except:
            continue
    return contacts, ", ".join(comments)


def get_messages(url):
    if not url:
        return ""
    res = make_request_hh(
        url, headers={"Authorization": f"Bearer {config.HH_TOKEN}", "User-Agent": "HH-User-Agent"}
    ).json()
    return res


async def get_telegram_id(cell, SESSION_STRING, API_ID, API_HASH):
    if SESSION_STRING is None:
        print("No session string")
        return "", 0
    cell = (
        cell.replace(" ", "")
        .replace("-", "")
        .replace("(", "")
        .replace(")", "")
        .replace("'", "")
    )
    print(cell)
    async with TelegramClient(
        StringSession(SESSION_STRING), int(API_ID), API_HASH
    ) as client:
        try:
            contact = InputPhoneContact(
                client_id=0, phone=cell, first_name="ABCd", last_name="abcd"
            )
            res = await client(ImportContactsRequest([contact]))
            if len(res.users) == 0:
                print("No user found")
            else:
                user_id = res.users[0].id

            await client(DeleteContactsRequest([InputUser(user_id, 0)]))
            return user_id, int(res.users[0].access_hash)
        except Exception as e:
            print(e)
            return "", 0


def extract_drive_id(cv_link):
    import re
    if cv_link and isinstance(cv_link, str):
        match = re.match(r'^https://drive\.google\.com/uc\?id=(.+)$', cv_link)
        if match and match.group(1):
            return f"https://drive.google.com/file/d/{match.group(1)}/view"
    else:
        print(f"cv_link {cv_link}")
    return cv_link

async def append_applicants_to_spreadsheet(spreadsheet_id, appliciants, vacancy):
    import re
    clients_sheet = gs.get_worksheet(1)
    clients_rows = clients_sheet.get_all_values()

    SESSION_STRING, API_ID, API_HASH = None, None, None
    active_clients = [1, 23]

    for i, row in enumerate(clients_rows[1:]):
        if len(row) > 3 and row[3] == "active":
            if str(row[4]) == "1":
                SESSION_STRING = row[2]
                API_ID = int(row[0])
                API_HASH = row[1]
            active_clients.append(i + 2)

    # filter already parsed
    sheet = gs.get_worksheet(0)
    already_parsed = set()
    for cv_url in sheet.col_values(12):
        try:
            already_parsed.add(cv_url.split("/")[-1])
        except Exception:
            pass

    for applicant in appliciants:
        try:
            if applicant["resume"]["id"] in already_parsed:
                continue
        except Exception:
            continue
        try:
            resume = applicant["resume"]
            pdflink = upload_file_from_resume(resume)

            contacts, contacts_comments = get_contacts(resume["id"])
            messaages = get_messages(applicant.get("messages_url", ""))

            # telegram_id, access_hash = await get_telegram_id(
            #     contacts.get("cell", ""), SESSION_STRING, API_ID, API_HASH
            # )
            telegram_id = ''
            access_hash = ''
            # telegram_id, access_hash = '', 0
            print(telegram_id)

            metadata = {"tg_hr": active_clients[0], "access_hash": access_hash}

            row = [
                [
                    applicant.get("created_at", ""),
                    resume.get("first_name", ""),
                    resume.get("last_name", ""),
                    resume.get("telegram", telegram_id),
                    resume.get("whatsapp", ""),
                    contacts.get("email", ""),
                    contacts.get("cell", ""),
                    contacts_comments,
                    re.sub(r'\s?\(Удаленно\)\s?|\s?\(удаленно\)\s?', '', vacancy.get("name", "")),
                    f"https://hh.ru/vacancy/{vacancy.get('id', '')}",
                    extract_drive_id(pdflink),
                    f"https://hh.ru/resume/{resume.get('id', '')}",
                    applicant["state"]["id"],
                    json.dumps(messaages),
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    "",
                    json.dumps(metadata),
                ]
            ]
            
            logger.info(row)

            response = append_data_to_sheet(spreadsheet_id, row, "Dialogs!A2")

            updated_range = response['updates']['updatedRange']
            row_number = int(updated_range.split('!')[1].split(':')[0][1:])

            formula = f'=B{row_number}&" "&C{row_number}&" has "& $R$1&R{row_number}&" | "&$S$1&S{row_number}&" | "&T{row_number}&" | "&U$1&U{row_number}'
            
            update_cell(spreadsheet_id, f"Dialogs!Q{row_number}", formula)

            await scoring(ScoringData(rows=[row_number], values=[pdflink]))

            update_cell(spreadsheet_id, f"Dialogs!AA{row_number}", 'Send wa')
        except Exception as e:
            logger.exception(e)
            continue