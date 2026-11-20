from __future__ import annotations

import re
import secrets
import uuid

import redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models import AppUser
from app.security import hash_password, verify_password

_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthError(Exception):
    def __init__(self, message: str, status_code: int = 400) -> None:
        super().__init__(message)
        self.status_code = status_code


def register(session: Session, email: str, password: str) -> AppUser:
    normalized = _normalize(email)
    if not _EMAIL.match(normalized):
        raise AuthError("Некорректный email")
    if len(password) < Constants.MIN_PASSWORD:
        raise AuthError(f"Пароль не короче {Constants.MIN_PASSWORD} символов")
    user = AppUser(email=normalized, password_hash=hash_password(password))
    session.add(user)
    try:
        session.flush()
    except IntegrityError as error:
        session.rollback()
        raise AuthError("Этот email уже зарегистрирован", 409) from error
    return user


def authenticate(session: Session, email: str, password: str, client_ip: str) -> AppUser:
    normalized = _normalize(email)
    limit_key = f"{Constants.LOGIN_PREFIX}{normalized}:{client_ip}"
    attempts = _client.incr(limit_key)
    if attempts == 1:
        _client.expire(limit_key, Constants.LOGIN_WINDOW_SECONDS)
    if attempts > Constants.LOGIN_MAX_ATTEMPTS:
        raise AuthError("Слишком много попыток входа, попробуйте позже", 429)
    user = session.scalars(select(AppUser).where(AppUser.email == normalized)).first()
    if user is None or not verify_password(password, user.password_hash):
        raise AuthError("Неверный email или пароль", 401)
    _client.delete(limit_key)
    return user


def create_session(user_id: uuid.UUID) -> str:
    token = secrets.token_urlsafe(Constants.TOKEN_BYTES)
    _client.setex(f"{Constants.SESSION_PREFIX}{token}", Constants.SESSION_TTL_SECONDS, str(user_id))
    return token


def user_id_for_session(token: str | None) -> uuid.UUID | None:
    if not token:
        return None
    raw = _client.get(f"{Constants.SESSION_PREFIX}{token}")
    return uuid.UUID(raw) if raw else None


def destroy_session(token: str | None) -> None:
    if token:
        _client.delete(f"{Constants.SESSION_PREFIX}{token}")


def _normalize(email: str) -> str:
    return email.strip().lower()


class Constants:
    MIN_PASSWORD = 8
    TOKEN_BYTES = 32
    SESSION_PREFIX = "session:"
    SESSION_TTL_SECONDS = 7 * 24 * 3600
    LOGIN_PREFIX = "login-attempts:"
    LOGIN_WINDOW_SECONDS = 300
    LOGIN_MAX_ATTEMPTS = 5
