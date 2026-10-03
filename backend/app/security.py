from __future__ import annotations

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
