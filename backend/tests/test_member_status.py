from datetime import datetime, timedelta, timezone

import pytest

from app.services.grid import member_status

NOW = datetime(2026, 12, 1, 12, 0, tzinfo=timezone.utc)


@pytest.mark.parametrize(
    "has_calendars,has_failed,synced_ago,expected",
    [
        (False, False, None, "no_calendars"),
        (False, True, None, "auth_failed"),
        (True, False, timedelta(minutes=5), "ok"),
        (True, False, timedelta(minutes=30), "ok"),
        (True, False, timedelta(minutes=31), "stale"),
        (True, False, None, "stale"),
        (True, True, timedelta(minutes=5), "ok"),
    ],
)
def test_member_status(has_calendars, has_failed, synced_ago, expected):
    synced = NOW - synced_ago if synced_ago is not None else None
    assert member_status(has_calendars, has_failed, synced, NOW) == expected
