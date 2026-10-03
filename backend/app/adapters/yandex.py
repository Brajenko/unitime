from __future__ import annotations

from datetime import datetime
from urllib.parse import urlencode

import httpx

from app.adapters import BusyOccurrence, DiscoveredCalendar
from app.adapters.caldav_ops import discover_with_client, fetch_busy_with_client
from app.config import settings


class YandexOAuthNotConfigured(RuntimeError):
    pass


def authorization_url(state: str) -> str:
    _require_oauth()
    query = urlencode(
        {
            "response_type": "code",
            "client_id": settings.yandex_client_id,
            "redirect_uri": settings.yandex_redirect_uri,
            "scope": Constants.SCOPE,
            "state": state,
        }
    )
    return f"{Constants.AUTHORIZE_URL}?{query}"


def exchange_code(code: str) -> dict:
    _require_oauth()
    response = httpx.post(
        Constants.TOKEN_URL,
        data={
            "grant_type": "authorization_code",
            "code": code,
            "client_id": settings.yandex_client_id,
            "client_secret": settings.yandex_client_secret,
        },
        timeout=Constants.TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    info = httpx.get(
        Constants.INFO_URL,
        headers={"Authorization": f"OAuth {payload['access_token']}"},
        timeout=Constants.TIMEOUT_SECONDS,
    )
    info.raise_for_status()
    profile = info.json()
    payload["email"] = profile.get("default_email") or profile.get("login")
    return payload


def refresh_access(refresh_token: str) -> dict:
    _require_oauth()
    response = httpx.post(
        Constants.TOKEN_URL,
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
            "client_id": settings.yandex_client_id,
            "client_secret": settings.yandex_client_secret,
        },
        timeout=Constants.TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def discover(secret: dict) -> list[DiscoveredCalendar]:
    return discover_with_client(Constants.CALDAV_ORIGIN, _authorization(secret))


def fetch_busy(
    secret: dict,
    calendar_url: str,
    window_start: datetime,
    window_end: datetime,
) -> list[BusyOccurrence]:
    return fetch_busy_with_client(
        Constants.CALDAV_ORIGIN,
        _authorization(secret),
        calendar_url,
        window_start,
        window_end,
    )


def _authorization(secret: dict) -> str:
    if secret.get("app_password"):
        import base64

        token = base64.b64encode(
            f"{secret['email']}:{secret['app_password']}".encode("utf-8")
        ).decode("ascii")
        return f"Basic {token}"
    return f"OAuth {secret['access_token']}"


def _require_oauth() -> None:
    if not settings.yandex_client_id or not settings.yandex_client_secret:
        raise YandexOAuthNotConfigured("Задайте YANDEX_CLIENT_ID и YANDEX_CLIENT_SECRET")


class Constants:
    AUTHORIZE_URL = "https://oauth.yandex.ru/authorize"
    TOKEN_URL = "https://oauth.yandex.ru/token"
    INFO_URL = "https://login.yandex.ru/info"
    CALDAV_ORIGIN = "https://caldav.yandex.ru"
    SCOPE = "calendar:all login:email"
    TIMEOUT_SECONDS = 20.0
