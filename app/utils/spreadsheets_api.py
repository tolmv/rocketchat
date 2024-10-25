import json

from telethon import TelegramClient
from telethon.sessions import StringSession
import random

from telethon.tl.types import InputPeerUser, PeerUser


def get_all_clients(gs):
    clients_sheet = gs.get_worksheet(1)
    clients_rows = clients_sheet.get_all_values()
    result = {}
    for i, row in enumerate(clients_rows[1:]):
        if len(row) > 3 and row[3] == "inactive":
            continue
        if len(row) > 3:
            try:
                result[i + 2] = TelegramClient(StringSession(row[2]), int(row[0]), row[1])
            except Exception as e:
                print(f"Ошибка при обработке строки {i + 2}: {e}")
        else:
            print(f"Недостаточно элементов в строке {i + 2}: {row}")
    return result


def make_client_inactive(gs, i):
    clients_sheet = gs.get_worksheet(1)
    clients_sheet.update_cell(i, 4, "inactive")


async def change_applicant_hr(gs, row, clients, metadata, telegram_id):
    clients_sheet = gs.get_worksheet(1)
    main_sheet = gs.get_worksheet(0)

    hr_id = int(metadata.get("tg_hr", -1))
    clients_sheet.update_cell(hr_id, 4, "inactive")

    clients_rows = clients_sheet.get_all_values()
    active_rows = [
        (i + 1, row) for i, row in enumerate(clients_rows) if row[3] == "active"
    ]
    random_row = random.choice(active_rows)

    metadata["tg_hr"] = random_row[0]
    main_sheet.update_cell(row, 25, json.dumps(metadata))

    new_client = clients[random_row[0]]
    access_hash = int(metadata.get("access_hash", 0))
    try:
        entity = await new_client.get_entity(PeerUser(int(telegram_id)))
    except ValueError:
        entity = await new_client.get_input_entity(
            InputPeerUser(int(telegram_id), access_hash=int(access_hash))
        )

    msg = "меня забанили, теперь пишу тут"
    await new_client.send_message(entity, msg)

    return clients[random_row[0]]
