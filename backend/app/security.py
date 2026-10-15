from __future__ import annotations

import hashlib
import hmac
import json
import os
from hashlib import sha256

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.config import settings


class SecretBox:
    def encrypt(self, payload: dict) -> bytes:
        nonce = os.urandom(Constants.NONCE_SIZE)
        token = _aesgcm().encrypt(nonce, json.dumps(payload).encode("utf-8"), None)
        return nonce + token

    def decrypt(self, blob: bytes) -> dict:
        nonce = blob[: Constants.NONCE_SIZE]
        token = blob[Constants.NONCE_SIZE :]
        raw = _aesgcm().decrypt(nonce, token, None)
        return json.loads(raw.decode("utf-8"))


def _aesgcm() -> AESGCM:
    key = sha256(settings.app_secret.encode("utf-8")).digest()
    return AESGCM(key)


secret_box = SecretBox()


class Constants:
    NONCE_SIZE = 12
    SALT_SIZE = 16
    SCRYPT_N = 2**14


def hash_password(password: str) -> str:
    salt = os.urandom(Constants.SALT_SIZE)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=Constants.SCRYPT_N, r=8, p=1, dklen=32)
    return f"scrypt${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str | None) -> bool:
    if not stored:
        return False
    try:
        scheme, salt_hex, digest_hex = stored.split("$")
    except ValueError:
        return False
    if scheme != "scrypt":
        return False
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=bytes.fromhex(salt_hex), n=Constants.SCRYPT_N, r=8, p=1, dklen=32
    )
    return hmac.compare_digest(digest.hex(), digest_hex)
