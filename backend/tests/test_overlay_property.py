"""Property-тест: алгоритм слотов против поминутного эталона.

Корректность: каждый слот, который алгоритм считает допустимым, свободен у всех на каждой минуте.
Полнота: каждая допустимая по эталону позиция слота на сетке найдена алгоритмом.
Прошлое: ни один слот не начинается раньше `now`.
"""
from datetime import date, datetime, time, timedelta

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from app.domain import BusyInterval, GridSpec, overlay
from app.domain import Constants as DomainConstants

DAY = date(2026, 9, 14)
TZ = DomainConstants.DISPLAY_TZ
MINUTES_IN_DAY = 24 * 60


def _at(day: int, minute: int) -> datetime:
    return datetime.combine(DAY + timedelta(days=day), time(0), tzinfo=TZ) + timedelta(minutes=minute)


intervals = st.lists(
    st.tuples(st.integers(0, 2), st.integers(0, MINUTES_IN_DAY - 1), st.integers(1, 300)),
    max_size=6,
)
participants = st.lists(intervals, min_size=1, max_size=4)
steps = st.sampled_from([15, 30, 60])
multipliers = st.integers(1, 4)
nows = st.tuples(st.integers(0, 2), st.integers(0, MINUTES_IN_DAY - 1))


def _build(raw):
    return [[BusyInterval(_at(day, start), _at(day, start) + timedelta(minutes=length)) for day, start, length in person] for person in raw]


def _reference_free(sources, start: datetime, minutes: int) -> bool:
    for minute in range(minutes):
        moment = start + timedelta(minutes=minute)
        for person in sources:
            if any(item.start <= moment < item.end for item in person):
                return False
    return True


@settings(max_examples=10_000, deadline=None, suppress_health_check=list(HealthCheck))
@given(raw=participants, step=steps, multiplier=multipliers, now=nows)
def test_slots_match_minute_by_minute_reference(raw, step, multiplier, now):
    sources = _build(raw)
    slot = step * multiplier
    spec = GridSpec(
        date_from=DAY,
        date_to=DAY + timedelta(days=2),
        time_start=time(9, 0),
        time_end=time(21, 0),
        step_minutes=step,
        slot_minutes=slot,
    )
    now_dt = _at(*now)
    result = overlay(sources, now_dt, spec)
    by_start = {cell.start: cell for cell in result.cells}
    cover = set()
    for cell in result.cells:
        window_end = datetime.combine(cell.start.date(), spec.time_end, tzinfo=TZ)
        fits = cell.start + timedelta(minutes=slot) <= window_end
        expected = fits and cell.start >= now_dt and _reference_free(sources, cell.start, slot)
        assert cell.slot_start == expected, (cell.start, slot)
        if cell.slot_start:
            for offset in range(multiplier):
                cover.add(cell.start + timedelta(minutes=step * offset))
    assert {cell.start for cell in result.cells if cell.in_slot} == cover
    assert all(by_start[start].start >= now_dt for start in cover) or not cover
