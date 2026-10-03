from __future__ import annotations

from datetime import datetime, timezone

from app.adapters import BusyOccurrence, DiscoveredCalendar
from app.adapters.caldav_client import CalDavAuthError, CalDavClient, CalDavError
from app.adapters.ical import occurrences_from_ics


def discover_with_client(origin: str, authorization: str) -> list[DiscoveredCalendar]:
    client = CalDavClient(origin=origin, authorization=authorization)
    try:
        calendars = client.discover_calendars()
    except CalDavAuthError:
        raise
    except CalDavError:
        raise
    finally:
        client.close()
    return [
        DiscoveredCalendar(
            external_id=href,
            display_name=name,
            selected_by_default=_default_selected(name),
        )
        for href, name in calendars
    ]


def fetch_busy_with_client(
    origin: str,
    authorization: str,
    calendar_url: str,
    window_start: datetime,
    window_end: datetime,
) -> list[BusyOccurrence]:
    client = CalDavClient(origin=origin, authorization=authorization)
    try:
        payloads = client.fetch_calendar_data(
            calendar_url,
            _ical_utc(window_start),
            _ical_utc(window_end),
        )
    finally:
        client.close()
    found: list[BusyOccurrence] = []
    for payload in payloads:
        found.extend(occurrences_from_ics(payload, window_start, window_end))
    return found


def _default_selected(name: str) -> bool:
    lowered = name.lower()
    skip_tokens = (
        "birthday",
        "birthdays",
        "holidays",
        "день рождения",
        "дни рождения",
        "праздник",
        "праздники",
        "contacts",
        "контакты",
    )
    return not any(token in lowered for token in skip_tokens)


def _ical_utc(moment: datetime) -> str:
    return moment.astimezone(Constants.UTC).strftime("%Y%m%dT%H%M%SZ")


class Constants:
    UTC = timezone.utc
