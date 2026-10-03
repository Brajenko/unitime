from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from dateutil.rrule import rrulestr
from icalendar import Calendar, Event

from app.adapters import BusyOccurrence
from app.domain import Constants as DomainConstants


def occurrences_from_ics(payload: str, window_start: datetime, window_end: datetime) -> list[BusyOccurrence]:
    calendar = Calendar.from_ical(payload)
    found: list[BusyOccurrence] = []
    for component in calendar.walk("VEVENT"):
        found.extend(_expand_event(component, window_start, window_end))
    return found


def _expand_event(component: Event, window_start: datetime, window_end: datetime) -> list[BusyOccurrence]:
    status = str(component.get("STATUS", "")).upper()
    transp = str(component.get("TRANSP", "")).upper()
    if status == "CANCELLED" or transp == "TRANSPARENT":
        return []
    uid = str(component.get("UID") or "unknown")
    start_raw = component.get("DTSTART")
    if start_raw is None:
        return []
    start = _as_datetime(start_raw.dt)
    end = _event_end(component, start, start_raw.dt)
    exdates = _exdates(component)

    rrule_value = component.get("RRULE")
    if rrule_value is None:
        if start < window_end and end > window_start:
            return [BusyOccurrence(uid=uid, start=start, end=end)]
        return []

    duration = end - start
    ical_line = "RRULE:" + rrule_value.to_ical().decode("utf-8")
    rule = rrulestr(ical_line, dtstart=start)
    results: list[BusyOccurrence] = []
    for occurrence in rule.between(window_start, window_end, inc=True):
        occ_start = occurrence if occurrence.tzinfo else occurrence.replace(tzinfo=DomainConstants.DISPLAY_TZ)
        if occ_start in exdates:
            continue
        occ_end = occ_start + duration
        if occ_start < window_end and occ_end > window_start:
            results.append(BusyOccurrence(uid=uid, start=occ_start, end=occ_end))
    return results


def _event_end(component: Event, start: datetime, start_raw: date | datetime) -> datetime:
    end_raw = component.get("DTEND")
    if end_raw is not None:
        return _as_datetime(end_raw.dt)
    duration = component.get("DURATION")
    if duration is not None:
        return start + duration.dt
    if isinstance(start_raw, date) and not isinstance(start_raw, datetime):
        return start + timedelta(days=1)
    return start + timedelta(hours=1)


def _as_datetime(value: date | datetime) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=DomainConstants.DISPLAY_TZ)
        return value.astimezone(timezone.utc).astimezone(DomainConstants.DISPLAY_TZ)
    local_date = value
    return datetime.combine(local_date, time.min, tzinfo=DomainConstants.DISPLAY_TZ)


def _exdates(component: Event) -> set[datetime]:
    values = component.get("EXDATE")
    if not values:
        return set()
    stamps: set[datetime] = set()
    items = values if isinstance(values, list) else [values]
    for item in items:
        dts = item.dts if hasattr(item, "dts") else []
        for stamp in dts:
            stamps.add(_as_datetime(stamp.dt))
    return stamps


class Constants:
    FALLBACK_TZ = ZoneInfo("Europe/Moscow")
