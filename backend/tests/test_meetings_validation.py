from datetime import datetime, timedelta, timezone

import pytest

from app.services.meetings import validate_meeting_window

NOW = datetime(2026, 12, 1, 12, 0, tzinfo=timezone.utc)
START = datetime(2026, 12, 2, 10, 0, tzinfo=timezone.utc)


def test_valid_window_passes():
    validate_meeting_window(START, START + timedelta(hours=1), NOW)


@pytest.mark.parametrize(
    "start,end,fragment",
    [
        (START, START, "позже начала"),
        (START, START - timedelta(minutes=5), "позже начала"),
        (NOW - timedelta(minutes=5), NOW + timedelta(hours=1), "в прошлом"),
        (START, START + timedelta(hours=8, minutes=5), "8 часов"),
        (START + timedelta(minutes=3), START + timedelta(hours=1), "5 минутам"),
        (START, START + timedelta(minutes=62), "5 минутам"),
        (START.replace(second=30), START + timedelta(hours=1), "5 минутам"),
    ],
)
def test_invalid_windows_are_rejected(start, end, fragment):
    with pytest.raises(ValueError, match=fragment):
        validate_meeting_window(start, end, NOW)


def test_naive_datetimes_are_rejected():
    with pytest.raises(ValueError, match="часовым поясом"):
        validate_meeting_window(START.replace(tzinfo=None), START.replace(tzinfo=None) + timedelta(hours=1), NOW)


def test_eight_hours_exactly_is_allowed():
    validate_meeting_window(START, START + timedelta(hours=8), NOW)
