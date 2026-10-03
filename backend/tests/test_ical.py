from datetime import datetime, timedelta

from app.adapters.ical import occurrences_from_ics
from app.domain import Constants as DomainConstants


def test_skips_transparent_and_cancelled():
    window_start = datetime(2026, 9, 14, tzinfo=DomainConstants.DISPLAY_TZ)
    window_end = window_start + timedelta(days=7)
    payload = """BEGIN:VCALENDAR
BEGIN:VEVENT
UID:one
DTSTART:20260916T100000Z
DTEND:20260916T110000Z
TRANSP:TRANSPARENT
END:VEVENT
BEGIN:VEVENT
UID:two
DTSTART:20260916T120000Z
DTEND:20260916T130000Z
STATUS:CANCELLED
END:VEVENT
END:VCALENDAR
"""
    assert occurrences_from_ics(payload, window_start, window_end) == []


def test_expands_rrule_inside_window():
    window_start = datetime(2026, 9, 14, tzinfo=DomainConstants.DISPLAY_TZ)
    window_end = window_start + timedelta(days=7)
    payload = """BEGIN:VCALENDAR
BEGIN:VEVENT
UID:weekly
DTSTART:20260901T080000Z
DTEND:20260901T090000Z
RRULE:FREQ=WEEKLY;BYDAY=WE
END:VEVENT
END:VCALENDAR
"""
    found = occurrences_from_ics(payload, window_start, window_end)
    assert len(found) == 1
    assert found[0].uid == "weekly"


def test_all_day_blocks_full_local_day():
    window_start = datetime(2026, 9, 14, tzinfo=DomainConstants.DISPLAY_TZ)
    window_end = window_start + timedelta(days=7)
    payload = """BEGIN:VCALENDAR
BEGIN:VEVENT
UID:dayoff
DTSTART;VALUE=DATE:20260916
DTEND;VALUE=DATE:20260917
END:VEVENT
END:VCALENDAR
"""
    found = occurrences_from_ics(payload, window_start, window_end)
    assert len(found) == 1
    assert found[0].start.hour == 0
    assert (found[0].end - found[0].start) == timedelta(days=1)
