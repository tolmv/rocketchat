import os
import string
import base64
import secrets

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend

from cryptography.fernet import Fernet

import aiohttp
import keyring
from passlib.context import CryptContext

try:
    from config import (
        CLIENT_ID,
        STATE_LENTH,
        SHELTER_USERNAME,
        SHELTER_SYSTEM,
        ENC_PHRASE,
    )
except ModuleNotFoundError:
    from config import (
        REQUEST_TOKEN_URL,
        CLIENT_ID,
        STATE_LENTH,
        SHELTER_USERNAME,
        SHELTER_SYSTEM,
        ENC_PHRASE,
    )

cipher_suite = None


def get_fernet_key(salt: str):
    password = ENC_PHRASE.encode()

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt.encode(),
        iterations=100000,
        backend=default_backend(),
    )

    key = kdf.derive(password)
    # Ensure key is properly encoded for Fernet
    fernet_key = base64.urlsafe_b64encode(key)

    return fernet_key


def _generate(n: int) -> str:
    alphabet = string.ascii_letters + string.digits
    state = "".join(secrets.choice(alphabet) for _ in range(n))
    return state


async def get_auth_token() -> int:
    # generate state of client token for ownher ensure
    token_state = _generate(STATE_LENTH)
    os.environ["OAUTH_STATE"] = token_state
    # request to hh oauth service for initiate token generating
    token_request_url = (
        REQUEST_TOKEN_URL + f"&client_id={CLIENT_ID}" + f"&state={token_state}"
    )

    # TODO: remove it
    print(token_request_url)

    async with aiohttp.ClientSession() as session:
        async with session.get(token_request_url) as resp:
            return resp.status


def read_token() -> str:
    global cipher_suite

    if cipher_suite is None:
        raise ValueError("Can't read token, cipher suite is not initialized!")

    token = keyring.get_password(SHELTER_SYSTEM, SHELTER_USERNAME)
    decrypted_token = cipher_suite.decrypt(token.encode())
    return decrypted_token.decode()


def save_token(token: str) -> None:
    global cipher_suite

    key = get_fernet_key(_generate(32))
    cipher_suite = Fernet(key)

    encrypted_token = cipher_suite.encrypt(token.encode())
    keyring.set_password(SHELTER_SYSTEM, SHELTER_USERNAME, encrypted_token)


def check_state(state: str) -> bool:
    crypt_context = CryptContext(schemes=["sha256_crypt"])
    hashed_state = crypt_context.hash(os.environ["OAUTH_STATE"])
    return crypt_context.verify(state, hashed_state)
