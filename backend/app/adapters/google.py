from __future__ import annotations

from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx

from app.adapters import BusyOccurrence, DiscoveredCalendar
from app.adapters.caldav_ops import _default_selected
from app.config import settings


class GoogleOAuthNotConfigured(RuntimeError):
    pass


def authorization_url(state: str) -> str:
    _require_oauth()
    query = urlencode(
        {
            "client_id": settings.google_client_id,
            "redirect_uri": settings.google_redirect_uri,
            "response_type": "code",
            "scope": Constants.SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "state": state,
        }
    )
    return f"{Constants.AUTHORIZE_URL}?{query}"


def exchange_code(code: str) -> dict:
    _require_oauth()
    response = httpx.post(
        Constants.TOKEN_URL,
        data={
            "code": code,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "redirect_uri": settings.google_redirect_uri,
            "grant_type": "authorization_code",
        },
        timeout=Constants.TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    userinfo = httpx.get(
        Constants.USERINFO_URL,
        headers={"Authorization": f"Bearer {payload['access_token']}"},
        timeout=Constants.TIMEOUT_SECONDS,
    )
    userinfo.raise_for_status()
    payload["email"] = userinfo.json().get("email")
    return payload


def refresh_access(refresh_token: str) -> dict:
    _require_oauth()
    response = httpx.post(
        Constants.TOKEN_URL,
        data={
            "refresh_token": refresh_token,
            "client_id": settings.google_client_id,
            "client_secret": settings.google_client_secret,
            "grant_type": "refresh_token",
        },
        timeout=Constants.TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return response.json()


def discover(secret: dict) -> list[DiscoveredCalendar]:
    response = httpx.get(
        Constants.CALENDAR_LIST_URL,
        headers=_bearer(secret),
        params={"minAccessRole": "freeBusyReader"},
        timeout=Constants.TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    items = response.json().get("items") or []
    calendars: list[DiscoveredCalendar] = []
    for item in items:
        calendar_id = item.get("id")
        if not calendar_id:
            continue
        name = item.get("summary") or calendar_id
        selected = bool(item.get("primary")) or _default_selected(name)
        calendars.append(
            DiscoveredCalendar(
                external_id=calendar_id,
                display_name=name,
                selected_by_default=selected,
            )
        )
    return calendars


def fetch_busy(
    secret: dict,
    calendar_id: str,
    window_start: datetime,
    window_end: datetime,
) -> list[BusyOccurrence]:
    response = httpx.post(
        Constants.FREEBUSY_URL,
        headers={**_bearer(secret), "Content-Type": "application/json"},
        json={
            "timeMin": window_start.astimezone(timezone.utc).isoformat(),
            "timeMax": window_end.astimezone(timezone.utc).isoformat(),
            "timeZone": "Europe/Moscow",
            "items": [{"id": calendar_id}],
        },
        timeout=Constants.TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    payload = response.json()
    busy = (
        payload.get("calendars", {})
        .get(calendar_id, {})
        .get("busy")
        or []
    )
    found: list[BusyOccurrence] = []
    for index, block in enumerate(busy):
        start = datetime.fromisoformat(block["start"].replace("Z", "+00:00"))
        end = datetime.fromisoformat(block["end"].replace("Z", "+00:00"))
        found.append(
            BusyOccurrence(
                uid=f"{calendar_id}:{start.isoformat()}:{index}",
                start=start,
                end=end,
            )
        )
    return found


def _bearer(secret: dict) -> dict[str, str]:
    return {"Authorization": f"Bearer {secret['access_token']}"}


def _require_oauth() -> None:
    if not settings.google_client_id or not settings.google_client_secret:
        raise GoogleOAuthNotConfigured("Задайте GOOGLE_CLIENT_ID и GOOGLE_CLIENT_SECRET")


class Constants:
    AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
    CALENDAR_LIST_URL = "https://www.googleapis.com/calendar/v3/users/me/calendarList"
    FREEBUSY_URL = "https://www.googleapis.com/calendar/v3/freeBusy"
    SCOPE = " ".join(
        (
            "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
            "https://www.googleapis.com/auth/calendar.freebusy",
            "openid",
            "email",
        )
    )
    TIMEOUT_SECONDS = 20.0
