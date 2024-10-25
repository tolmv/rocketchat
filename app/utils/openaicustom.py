import json
import time
from routes.spreadsheet import MessageData
import httpx
import config
import openai
import requests
from pydantic import BaseModel
from typing import Optional, Dict, Any, Union

import asyncio

from loguru import logger
from typing import Union, List

class AgentResponse(BaseModel):
    message_content: str
    usage: Optional[Dict[str, Any]] = None
    model: str
    prompt: str


async def get_gpt_res(
    mentor_prompt: str = "",
    user_message: str = "",
    temperature: Optional[float] = 0.7,
    model: str = "gpt-3.5-turbo-1106",
    json_mode: bool = False,
) -> Union[str, AgentResponse] or None:
    if not isinstance(temperature, (float, int)):
        return "Temperature must be number!"

    try:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.OPENAI_API_KEY}",
        }
        request_body = {
            "model": model,
            "temperature": temperature,
            "messages": [
                {"role": "system", "content": mentor_prompt},
                {"role": "user", "content": user_message},
            ],
        }

        if json_mode:
            request_body["response_format"] = {"type": "json_object"}

        api_url = "https://api.openai.com/v1/chat/completions"
        if not model.startswith("gpt"):
            api_url = "https://api.endpoints.anyscale.com/v1/chat/completions"
            headers["Authorization"] = f"Bearer {config.ANYSCALE_API_KEY}"

        async with httpx.AsyncClient(timeout=300) as client:
            response = await client.post(api_url, headers=headers, json=request_body)
            logger.info(response.json())
            data = response.json()
            return_data = {
                "message_content": str(data["choices"][0]["message"]["content"]),
                "usage": data.get("usage", None),
                "model": str(model),
                "prompt": str(mentor_prompt),
            }
            logger.info(return_data)
            return AgentResponse(**return_data)
    except Exception as e:
        logger.exception(e)
        return None
    
async def call_assistant(user_message: str = "", json_mode: bool = False) -> Union[str, list]:
    client_open_ai = openai.OpenAI(api_key=config.OPENAI_HR_API_KEY)
    try:
        # Создаем поток
        thread = client_open_ai.beta.threads.create()

        # Добавляем сообщение в поток
        message = client_open_ai.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=user_message
        )

        # Создаем и выполняем запуск
        run = client_open_ai.beta.threads.runs.create_and_poll(
            thread_id=thread.id,
            assistant_id=config.ASSISTANT_CV_SCORE
        )

        if run.status == 'completed': 
            # Получаем список сообщений
            messages = client_open_ai.beta.threads.messages.list(
                thread_id=thread.id
            )
            return messages.data
        else:
            return f"Run status: {run.status}"

    except Exception as e:
        logger.exception(f"An error occurred during the API call. {e}")
        return str(e)
    
async def call_assistant_history(user_history: List[MessageData], assistant_id: str, api_key: str, json_mode: bool = False) -> Union[str, list]:
    client_open_ai = openai.OpenAI(api_key=api_key)
    try:
        # Создаем поток
        thread = client_open_ai.beta.threads.create()

        #напиши цикл который пройдёт по user_history
        for message_data in user_history:   
            message = client_open_ai.beta.threads.messages.create(
                thread_id=thread.id,
                role=message_data.role,
                content=message_data.text
            )

        # Создаем и выполняем запуск
        run = client_open_ai.beta.threads.runs.create_and_poll(
            thread_id=thread.id,
            assistant_id=assistant_id,
        )

        if run.status == 'completed': 
            # Получаем список сообщений
            messages = client_open_ai.beta.threads.messages.list(
                thread_id=thread.id
            )
            return messages.data
        else:
            return f"Run status: {run.status}"

    except Exception as e:
        logger.exception(f"An error occurred during the API call. {e}")
        return str(e)

async def call_assistant_custom(user_message: str, role: str, assistant_id: str, api_key: str, json_mode: bool = False) -> Union[str, dict]:
    client_open_ai = openai.OpenAI(api_key=api_key)
    try:
        # Создаем поток
        thread = client_open_ai.beta.threads.create()

        # Добавляем сообщение в поток
        message = client_open_ai.beta.threads.messages.create(
            thread_id=thread.id,
            role=role,
            content=user_message
        )

        # Создаем и выполняем запуск
        run = client_open_ai.beta.threads.runs.create_and_poll(
            thread_id=thread.id,
            assistant_id=assistant_id,
        )

        result = None
        tool_outputs = []
        logger.info(f"Run status: {run.status}")
        # Проверка, если требуется действие и есть вызов функции
        if run.status == 'requires_action' and run.required_action and run.required_action.submit_tool_outputs:
            for tool_call in run.required_action.submit_tool_outputs.tool_calls:
                args = json.loads(tool_call.function.arguments)
                
                if tool_call.function.name == 'verify_user':
                    phone_number = args.get('phone_number')
                    telegram_id = args.get('telegram_id')
                    refCode = args.get('refCode')
                    isPartnerMentioned = args.get('isPartnerMentioned')
                    generate_referral_link(phone_number, telegram_id, refCode)
                    tool_outputs.append({
                        "tool_call_id": tool_call.id,
                        "output": ''
                    })

                elif tool_call.function.name == 'generate_referral_link':
                    phone_number = args.get('phone_number')
                    telegram_id = args.get('telegram_id')
                    refCode = args.get('refCode')
                    result = generate_referral_link(phone_number, telegram_id, refCode)
                    logger.info(f"Result of generate_referral_link: {result}")
                    tool_outputs.append({
                        "tool_call_id": tool_call.id,
                        "output": f'Your referral link is {json.dumps(result)}. Share it!'
                    })

                elif tool_call.function.name == 'generate_calendly_link':
                    website_link = args.get('website_link')
                    asked_about_website = args.get('asked_about_website')
                    phone_number = args.get('phone_number')
                    telegram_id = args.get('telegram_id')
                    ref_code = args.get('ref_code')
                    result1 = generate_calendly_link(website_link, asked_about_website, ref_code, phone_number, telegram_id)
                    logger.info(f"Result of generate_calendly_link: {result1}")
                    tool_outputs.append({
                        "tool_call_id": tool_call.id,
                        "output": f'If you want to list a token, please schedule a meeting at {json.dumps(result1)}.'
                    })

                elif tool_call.function.name == 'get_crypto_price':
                    crypto = args.get('crypto')
                    date = args.get('date')
                    result1 = get_crypto_price(crypto, date)
                    logger.info(f"Result of get_crypto_price: {result1}")
                    tool_outputs.append({
                        "tool_call_id": tool_call.id,
                        "output": result1
                    })

                elif tool_call.function.name == 'get_crypto_news':
                    crypto = args.get('crypto')
                    date = args.get('date')
                    result1 = get_crypto_news(crypto, date)
                    tool_outputs.append({
                        "tool_call_id": tool_call.id,
                        "output": 'All news: ' + json.dumps(result1)
                    })

            # Проверка содержимого tool_outputs перед отправкой
            logger.info(f"Tool outputs to be submitted: {tool_outputs}")

            if tool_outputs:
                client_open_ai.beta.threads.runs.submit_tool_outputs(
                    thread_id=thread.id,
                    run_id=run.id,
                    tool_outputs=tool_outputs
                )

        repeat = 0

        while repeat <= 10:
            if run.status == 'completed':
                # Получаем список сообщений
                messages = client_open_ai.beta.threads.messages.list(
                    thread_id=thread.id
                )

                # Ищем новое сообщение ассистента
                for message in messages:
                    if message.role == 'assistant':
                        message_with_result = {
                            **dict(message),
                            "result": result
                        }

                        logger.info(message_with_result)

                        return message_with_result

            logger.info(f"Run status: {run.status}")
            await asyncio.sleep(1)

            run = client_open_ai.beta.threads.runs.retrieve(
                thread_id=thread.id,
                run_id=run.id
            )

            repeat += 1
            
        logger.info('log1')
        return {"status": run.status}

    except Exception as e:
        logger.exception(f"An error occurred during the API call. {e}")
        return {"error": str(e)}
 

def generate_referral_link(phone_number: str = None, telegram_id: str = None, refCode: str = None) -> dict:
    url = "https://api.latoken.com/growth-platform-api/referral/chat"
    
    # Проверяем, какой из параметров передан
    if phone_number:
        payload = {
            "phone": phone_number,
            "refCode": refCode
        }
    elif telegram_id:
        payload = {
            "telegram": telegram_id,
            "refCode": refCode
        }
    else:
        return {"error": "Необходимо предоставить либо номер телефона, либо ID в Telegram"}
    
    headers = {
        "Content-Type": "application/json"
    }

    try:
        response = requests.post(url, json=payload, headers=headers)
        response.raise_for_status()
        response_data = response.json()
        logger.info(response_data)
        referral_code = response_data.get('code')
        short_chat_link = response_data.get('shortChatLink')
        
        if short_chat_link:
            referral_link = f"{short_chat_link}"
            
            return {"referral_link": referral_link}
        else:
            return {"error": "Код не найден в ответе"}
    except requests.exceptions.RequestException as e:
        logger.exception("Failed to send contact information: " + str(e))
        return {"error": "Произошла ошибка при отправке контактной информации"}

def generate_calendly_link(website_link, asked_about_website, ref_code, phone_number=None, telegram_id=None):
    if not asked_about_website:
        return "Ask the lead if they have a website?"

    # Замена "no_website" на пустое значение
    if website_link == "no_website":
        website_link = ""

    logger.info(f"generate_calendly_link: {website_link}, {asked_about_website}, {ref_code}, {phone_number}, {telegram_id}")

    try:
        base_url = "https://api.latoken.com/growth-platform-api/crm/chat-lead"
        params = {
            'web': website_link if website_link else '',
            'phone': phone_number if phone_number else '',
            'tg': telegram_id if telegram_id else '',
            'ref': ref_code if ref_code else ''
        }
        query_string = '&'.join([f"{key}={value}" for key, value in params.items() if value])
        lead_data_url = f"{base_url}?{query_string}"

        try:
            response = requests.get(lead_data_url)
            response.raise_for_status()
            lead_data = response.json()
            logger.info(lead_data)
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching lead data: {e}")
            return "Error fetching lead data"

        responsible_user_id = lead_data.get('responsible_user_id')
        if responsible_user_id == 8872970:
            return "https://calendly.com/itunu-ola/30min."
        elif responsible_user_id == 9811374:
            return "https://calendly.com/chris-serrano-0x/30min"
        
    except Exception as e:
        logger.error(f"Error generating Calendly link: {e}")

    return "https://calendly.com/growth-activities/growth-platform"

def get_crypto_price(crypto, date=None):
    from datetime import datetime
    logger.info(crypto + ' ' + str(date))
    if date:
        try:
            # Преобразуем дату в нужный формат
            date_obj = datetime.strptime(date, '%Y-%m-%d')
            formatted_date = date_obj.strftime('%d-%m-%Y')
        except ValueError:
            return "Invalid date format. Please use YYYY-MM-DD."
        
        # Запрос для получения исторических данных
        url = f"https://api.coingecko.com/api/v3/coins/{crypto}/history?date={formatted_date}"
    else:
        # Запрос для получения текущей цены teest1
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={crypto}&vs_currencies=usd"
    
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if date:
            # Получение цены из исторических данных
            price = data.get('market_data', {}).get('current_price', {}).get('usd')
        else:
            # Получение текущей цены
            price = data.get(crypto, {}).get('usd')
        
        if price is not None:
            return f"The price of {crypto} on {date if date else 'current date'} is ${price}"
        else:
            return "Invalid cryptocurrency symbol or data not available for the specified date."
    else:
        return "Failed to fetch the cryptocurrency price."
    
def get_crypto_news(crypto, date=None):
    from datetime import datetime
    api_key = "12fc47cfe60c4ec1883fa5678df826f7"
    
    if date:
        try:
            # Преобразуем дату в нужный формат
            date_obj = datetime.strptime(date, '%Y-%m-%d')
            formatted_date = date_obj.strftime('%Y-%m-%d')
        except ValueError:
            return "Invalid date format. Please use YYYY-MM-DD."
        
        # Запрос для получения новостей на указанную дату
        url = f"https://newsapi.org/v2/everything?q={crypto}&from={formatted_date}&to={formatted_date}&sortBy=publishedAt&apiKey={api_key}"
    else:
        # Запрос для получения последних новостей
        url = f"https://newsapi.org/v2/everything?q={crypto}&sortBy=publishedAt&apiKey={api_key}"
    
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        articles = data.get('articles', [])
        
        if articles:
            news_list = []
            for article in articles:
                news_item = {
                    "title": article.get('title'),
                    "description": article.get('description'),
                    "url": article.get('url'),
                    "publishedAt": article.get('publishedAt')
                }
                news_list.append(news_item)
            return news_list
        else:
            return "No news articles found for this cryptocurrency."
    else:
        return "Failed to fetch the news."
