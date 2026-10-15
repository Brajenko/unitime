from __future__ import annotations

import hashlib
import json
import uuid

import redis

from app.config import settings

_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)


def bump_user(user_id: uuid.UUID) -> None:
    """Данные пользователя изменились (синк, выбор календарей, статус): старые ключи сетки перестают совпадать."""
    try:
        _client.incr(f"{Constants.VERSION_PREFIX}{user_id}")
    except redis.RedisError:
        pass


def grid_key(user_ids: list[uuid.UUID], params: dict) -> str:
    ordered = sorted(user_ids, key=str)
    try:
        versions = _client.mget([f"{Constants.VERSION_PREFIX}{item}" for item in ordered])
    except redis.RedisError:
        versions = [None] * len(ordered)
    material = json.dumps(
        {"users": [[str(item), version or "0"] for item, version in zip(ordered, versions)], "params": params},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[: Constants.KEY_LENGTH]


def get(key: str) -> str | None:
    if not settings.grid_cache_enabled:
        return None
    try:
        return _client.get(f"{Constants.GRID_PREFIX}{key}")
    except redis.RedisError:
        return None


def put(key: str, payload: str) -> None:
    if not settings.grid_cache_enabled:
        return
    try:
        _client.setex(f"{Constants.GRID_PREFIX}{key}", Constants.TTL_SECONDS, payload)
    except redis.RedisError:
        pass


class Constants:
    VERSION_PREFIX = "data-version:"
    GRID_PREFIX = "grid:"
    TTL_SECONDS = 300
    KEY_LENGTH = 32
