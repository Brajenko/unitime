from datetime import date, datetime, time, timedelta

from app.domain import BusyInterval, GridSpec, overlay, suggest_slot, validate_grid_spec
from app.domain import Constants as DomainConstants


def test_overlay_counts_free_calendars():
    week = date(2026, 9, 14)
    busy_a = [
        BusyInterval(
            _at(week, 2, 11),
            _at(week, 2, 13),
        )
    ]
    busy_b = [
        BusyInterval(
            _at(week, 2, 15),
            _at(week, 2, 16),
        )
    ]
    result = overlay([busy_a, busy_b], _at(week, 0, 9), _week_spec(week))
    wed_11 = next(cell for cell in result.cells if cell.day_index == 2 and cell.hour == 11)
    wed_14 = next(cell for cell in result.cells if cell.day_index == 2 and cell.hour == 14)
    assert wed_11.free_count == 1
    assert wed_14.free_count == 2
    assert result.total == 2


def test_suggest_slot_prefers_weekday_two_hours():
    week = date(2026, 9, 14)
    spec = _week_spec(week, slot_minutes=120)
    cells = overlay([[], [], []], _at(week, 2, 10), spec).cells
    slot = suggest_slot(cells, 3, _at(week, 0, 8), spec)
    assert slot is not None
    assert slot.start.weekday() < 5
    duration = (slot.end - slot.start).total_seconds() / 3600
    assert duration == 2


def test_busy_blocks_suggested_common_free():
    week = date(2026, 9, 14)
    all_day_busy = [
        BusyInterval(_at(week, day, 9), _at(week, day, 21))
        for day in range(7)
        if day != 2
    ]
    wed_busy = [
        BusyInterval(_at(week, 2, 9), _at(week, 2, 14)),
        BusyInterval(_at(week, 2, 17), _at(week, 2, 21)),
    ]
    result = overlay([all_day_busy + wed_busy], _at(week, 2, 9), _week_spec(week, slot_minutes=180))
    assert result.suggested is not None
    assert result.suggested.start == _at(week, 2, 14)
    assert result.suggested.end == _at(week, 2, 17)


def test_overlay_respects_step_and_day_window():
    week = date(2026, 9, 14)
    spec = GridSpec(
        date_from=week,
        date_to=week + timedelta(days=4),
        time_start=time(10, 0),
        time_end=time(12, 0),
        step_minutes=15,
        slot_minutes=60,
    )
    result = overlay([[]], _at(week, 0, 9), spec)
    assert {cell.day_index for cell in result.cells} == {0, 1, 2, 3, 4}
    monday = [cell for cell in result.cells if cell.day_index == 0]
    assert len(monday) == 8
    assert monday[0].hour == 10
    assert monday[0].minute == 0
    assert monday[1].minute == 15
    assert monday[-1].hour == 11
    assert monday[-1].minute == 45


def test_validate_grid_spec_rejects_inverted_range():
    try:
        validate_grid_spec(date(2026, 9, 20), date(2026, 9, 14), "09:00", "18:00", 30, 60)
        assert False
    except ValueError:
        pass


def test_suggest_slots_one_per_free_run():
    week = date(2026, 9, 14)
    spec = _week_spec(week, slot_minutes=60)
    result = overlay([[], []], _at(week, 0, 8), spec)
    assert len(result.slots) == 7
    assert result.suggested is not None
    assert result.suggested.start == result.slots[0].start


def _week_spec(week: date, slot_minutes: int = 60) -> GridSpec:
    return GridSpec(
        date_from=week,
        date_to=week + timedelta(days=6),
        time_start=time(9, 0),
        time_end=time(21, 0),
        step_minutes=60,
        slot_minutes=slot_minutes,
    )


def _at(week: date, day: int, hour: int) -> datetime:
    return datetime.combine(week + timedelta(days=day), datetime.min.time(), tzinfo=DomainConstants.DISPLAY_TZ).replace(
        hour=hour
    )
