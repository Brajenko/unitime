from datetime import datetime, timedelta, timezone

import pytest
from hypothesis import given, settings, strategies as st

from app.domain import BusyInterval, free_to_busy
from app.services.availability import validate_windows
from app.services.grid import member_status

T0 = datetime(2026, 12, 1, 0, 0, tzinfo=timezone.utc)
T1 = T0 + timedelta(days=1)


def at(hour: int, minute: int = 0) -> datetime:
    return T0 + timedelta(hours=hour, minutes=minute)


def spans(items):
    return [(item.start, item.end) for item in items]


def test_no_windows_means_busy_whole_range():
    assert spans(free_to_busy([], T0, T1)) == [(T0, T1)]


def test_window_in_the_middle_splits_busy_in_two():
    assert spans(free_to_busy([BusyInterval(at(10), at(12))], T0, T1)) == [(T0, at(10)), (at(12), T1)]


def test_window_covering_range_leaves_nothing_busy():
    assert free_to_busy([BusyInterval(T0, T1)], T0, T1) == []


def test_adjacent_and_overlapping_windows_are_merged():
    free = [BusyInterval(at(10), at(11)), BusyInterval(at(11), at(12)), BusyInterval(at(11, 30), at(13))]
    assert spans(free_to_busy(free, T0, T1)) == [(T0, at(10)), (at(13), T1)]


def test_windows_outside_range_are_clipped():
    free = [BusyInterval(T0 - timedelta(hours=2), at(1)), BusyInterval(at(23), T1 + timedelta(hours=3))]
    assert spans(free_to_busy(free, T0, T1)) == [(at(1), at(23))]
    assert spans(free_to_busy([BusyInterval(T1, T1 + timedelta(hours=1))], T0, T1)) == [(T0, T1)]


@settings(max_examples=300)
@given(st.lists(st.tuples(st.integers(-120, 1560), st.integers(1, 600)), max_size=8), st.integers(0, 1439))
def test_minute_is_busy_iff_not_inside_free_window(raw, probe):
    free = [BusyInterval(T0 + timedelta(minutes=start), T0 + timedelta(minutes=start + length)) for start, length in raw]
    busy = free_to_busy(free, T0, T1)
    point = T0 + timedelta(minutes=probe)
    is_free = any(item.start <= point < item.end for item in free)
    is_busy = any(item.start <= point < item.end for item in busy)
    assert is_busy == (not is_free)
    assert all(earlier.end < later.start for earlier, later in zip(busy, busy[1:]))


@pytest.mark.parametrize(
    "start,end,fragment",
    [
        (at(12), at(10), "позже начала"),
        (at(10), at(10), "позже начала"),
        (at(10, 3), at(11), "5 минутам"),
        (T0 - timedelta(hours=1), at(1), "диапазон"),
        (at(23), T1 + timedelta(hours=1), "диапазон"),
    ],
)
def test_validate_windows_rejects_bad_input(start, end, fragment):
    with pytest.raises(ValueError, match=fragment):
        validate_windows([BusyInterval(start, end)], T0, T1)


def test_validate_windows_limits_count_and_accepts_edges():
    validate_windows([BusyInterval(T0, T1)], T0, T1)
    many = [BusyInterval(at(0, 5 * i), at(0, 5 * i + 5)) for i in range(501)]
    with pytest.raises(ValueError, match="500"):
        validate_windows(many, T0, T1 + timedelta(days=2))


def test_member_status_manual_and_calendar_wins():
    now = at(12)
    assert member_status(False, False, None, now, has_manual=True) == "manual"
    assert member_status(False, True, None, now, has_manual=True) == "manual"
    assert member_status(True, False, now - timedelta(minutes=5), now, has_manual=True) == "ok"
    assert member_status(False, False, None, now) == "no_calendars"
