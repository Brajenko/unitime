from __future__ import annotations

import secrets
import json

import redis

from app.config import settings

_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)


def put_state(provider: str) -> str:
    token = secrets.token_urlsafe(Constants.STATE_BYTES)
    _client.setex(f"{Constants.PREFIX}{token}", Constants.TTL_SECONDS, json.dumps({"provider": provider}))
    return token


def pop_state(token: str) -> dict | None:
    key = f"{Constants.PREFIX}{token}"
    raw = _client.get(key)
    if raw is None:
        return None
    _client.delete(key)
    return json.loads(raw)


class Constants:
    PREFIX = "oauth-state:"
    TTL_SECONDS = 600
    STATE_BYTES = 24
