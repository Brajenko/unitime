"""Кейсы ingest: таблица «календарь × случай» для слайда RAT (T4)."""
from datetime import datetime, timedelta, timezone

from app.adapters.ical import occurrences_from_ics
from app.domain import Constants as DomainConstants

TZ = DomainConstants.DISPLAY_TZ
WINDOW_START = datetime(2026, 9, 14, tzinfo=TZ)
WINDOW_END = WINDOW_START + timedelta(days=7)


def _wrap(*events: str) -> str:
    return "BEGIN:VCALENDAR\nVERSION:2.0\n" + "\n".join(events) + "\nEND:VCALENDAR\n"


def _event(body: str) -> str:
    return "BEGIN:VEVENT\n" + body.strip() + "\nEND:VEVENT"


def _run(*events: str):
    return occurrences_from_ics(_wrap(*events), WINDOW_START, WINDOW_END)


def test_exdate_skips_one_instance():
    found = _run(
        _event(
            """
UID:weekly
DTSTART:20260902T080000Z
DTEND:20260902T090000Z
RRULE:FREQ=WEEKLY;BYDAY=WE
EXDATE:20260916T080000Z
"""
        )
    )
    assert found == []


def test_moved_instance_replaces_original():
    found = _run(
        _event(
            """
UID:lecture
DTSTART:20260902T080000Z
DTEND:20260902T090000Z
RRULE:FREQ=WEEKLY;BYDAY=WE
"""
        ),
        _event(
            """
UID:lecture
RECURRENCE-ID:20260916T080000Z
DTSTART:20260917T150000Z
DTEND:20260917T160000Z
"""
        ),
    )
    assert [item.start for item in found] == [datetime(2026, 9, 17, 15, tzinfo=timezone.utc)]


def test_timezone_is_converted_to_display_zone():
    found = _run(
        _event(
            """
UID:ny
DTSTART;TZID=America/New_York:20260915T090000
DTEND;TZID=America/New_York:20260915T100000
"""
        )
    )
    assert len(found) == 1
    assert found[0].start.astimezone(TZ).hour == 16
    assert found[0].end - found[0].start == timedelta(hours=1)


def test_event_across_midnight_is_kept_whole():
    found = _run(
        _event(
            """
UID:night
DTSTART:20260915T200000Z
DTEND:20260916T020000Z
"""
        )
    )
    assert len(found) == 1
    assert found[0].end - found[0].start == timedelta(hours=6)


def test_event_started_before_window_is_included():
    found = _run(
        _event(
            """
UID:long
DTSTART:20260913T200000Z
DTEND:20260914T040000Z
"""
        )
    )
    assert len(found) == 1


def test_recurring_event_started_before_window_overlapping_it():
    found = _run(
        _event(
            """
UID:overnight
DTSTART:20260906T200000Z
DTEND:20260907T040000Z
RRULE:FREQ=WEEKLY
"""
        )
    )
    assert any(item.start < WINDOW_START < item.end for item in found)


def test_titles_are_not_carried_into_occurrences():
    found = _run(
        _event(
            """
UID:secret
SUMMARY:Приём у врача
DESCRIPTION:очень личное
LOCATION:Клиника
DTSTART:20260915T080000Z
DTEND:20260915T090000Z
"""
        )
    )
    assert len(found) == 1
    assert set(vars(found[0])) == {"uid", "start", "end"}
