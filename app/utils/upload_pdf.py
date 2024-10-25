from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

import requests
import os
import pickle
import config

# Path to your client_secrets.json
CREDENTIALS_FILE = "hh/client_secrets.json"
# If modifying these scopes, delete the file token.pickle.
SCOPES = ["https://www.googleapis.com/auth/drive.file"]


def service_account_login():
    creds = None
    # The file token.pickle stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists("token.pickle"):
        with open("token.pickle", "rb") as token:
            creds = pickle.load(token)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open("token.pickle", "wb") as token:
            pickle.dump(creds, token)

    return build("drive", "v3", credentials=creds)


def upload_file(filename, filepath, mimetype):
    credentials = service_account.Credentials.from_service_account_file(
        "./data/service_account_file.json", scopes=["https://www.googleapis.com/auth/drive"]
    )

    # Create a service object
    service = build("drive", "v3", credentials=credentials)
    file_metadata = {"name": filename}
    media = MediaFileUpload(filepath, mimetype=mimetype)
    file = (
        service.files()
        .create(body=file_metadata, media_body=media, fields="id")
        .execute()
    )

    file_id = file.get("id")
    service.permissions().create(
        fileId=file_id, body={"type": "anyone", "role": "reader"}
    ).execute()

    return f"https://drive.google.com/uc?id={file_id}"


def upload_file_from_resume(resume):
    from utils.hhparse import make_request_hh
    id = resume["id"]
    with open("result.pdf", "wb") as f:
        f.write(
            make_request_hh(
                resume["download"]["pdf"]["url"],
                headers={
                    "Authorization": f"Bearer {config.HH_TOKEN}",
                    "User-Agent": "HH-User-Agent",
                },
            ).content
        )

    return upload_file(f"{id}.pdf", "result.pdf", "application/pdf")


def append_data_to_sheet(spreadsheet_id, data, range_name):
    # Authenticate with service account credentials
    credentials = service_account.Credentials.from_service_account_file(
        "./data//service_account_file.json",
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )

    # Create a service object
    service = build("sheets", "v4", credentials=credentials)

    # Build the request body
    value_input_option = (
        "USER_ENTERED"  # Determines how input data should be interpreted
    )
    insert_data_option = "OVERWRITE"  # Determines how existing data should be changed
    value_range_body = {"values": data}

    # Execute the request to append data
    request = (
        service.spreadsheets()
        .values()
        .append(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption=value_input_option,
            insertDataOption=insert_data_option,
            body=value_range_body,
        )
    )
    response = request.execute()
    return response

def update_cell(spreadsheet_id, cell_range, value):
    credentials = service_account.Credentials.from_service_account_file(
        "./data/service_account_file.json",
        scopes=["https://www.googleapis.com/auth/spreadsheets"]
    )

    service = build("sheets", "v4", credentials=credentials)

    value_range_body = {
        "values": [[value]],
        "majorDimension": "ROWS"
    }

    request = service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=cell_range,
        valueInputOption="USER_ENTERED",
        body=value_range_body
    )

    response = request.execute()

    return response