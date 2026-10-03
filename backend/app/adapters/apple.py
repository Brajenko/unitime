from __future__ import annotations

from datetime import datetime

from app.adapters import BusyOccurrence, DiscoveredCalendar
from app.adapters.caldav_ops import discover_with_client, fetch_busy_with_client


def discover(secret: dict) -> list[DiscoveredCalendar]:
    return discover_with_client(Constants.CALDAV_ORIGIN, _basic(secret))


def fetch_busy(
    secret: dict,
    calendar_url: str,
    window_start: datetime,
    window_end: datetime,
) -> list[BusyOccurrence]:
    origin = _origin_from_url(calendar_url)
    return fetch_busy_with_client(
        origin,
        _basic(secret),
        calendar_url,
        window_start,
        window_end,
    )


def _basic(secret: dict) -> str:
    import base64

    raw = f"{secret['email']}:{secret['app_password']}".encode("utf-8")
    return "Basic " + base64.b64encode(raw).decode("ascii")


def _origin_from_url(url: str) -> str:
    from urllib.parse import urlparse

    parsed = urlparse(url)
    if parsed.scheme and parsed.netloc:
        return f"{parsed.scheme}://{parsed.netloc}"
    return Constants.CALDAV_ORIGIN


class Constants:
    CALDAV_ORIGIN = "https://caldav.icloud.com"
