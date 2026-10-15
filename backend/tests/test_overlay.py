from datetime import date, datetime, time, timedelta

from app.domain import BusyInterval, GridSpec, overlay, validate_grid_spec
from app.domain import Constants as DomainConstants


def test_overlay_counts_free_calendars():
    week = date(2026, 9, 14)
    busy_a = [BusyInterval(_at(week, 2, 11), _at(week, 2, 13))]
    busy_b = [BusyInterval(_at(week, 2, 15), _at(week, 2, 16))]
    result = overlay([busy_a, busy_b], _at(week, 0, 9), _week_spec(week))
    wed_11 = next(cell for cell in result.cells if cell.day_index == 2 and cell.hour == 11)
    wed_14 = next(cell for cell in result.cells if cell.day_index == 2 and cell.hour == 14)
    assert wed_11.free_count == 1
    assert wed_14.free_count == 2
    assert result.total == 2


def test_slot_start_marks_every_position_where_slot_fits():
    week = date(2026, 9, 14)
    busy = [BusyInterval(_at(week, 2, 9), _at(week, 2, 12)), BusyInterval(_at(week, 2, 16), _at(week, 2, 21))]
    spec = _week_spec(week, slot_minutes=120)
    result = overlay([busy], _at(week, 0, 8), spec)
    wednesday = [cell for cell in result.cells if cell.day_index == 2]
    starts = [cell.hour for cell in wednesday if cell.slot_start]
    covered = [cell.hour for cell in wednesday if cell.in_slot]
    assert starts == [12, 13, 14]
    assert covered == [12, 13, 14, 15]


def test_slot_does_not_cross_busy_or_day_boundary():
    week = date(2026, 9, 14)
    spec = _week_spec(week, slot_minutes=180)
    result = overlay([[BusyInterval(_at(week, 0, 12), _at(week, 0, 13))]], _at(week, 0, 8), spec)
    monday = [cell for cell in result.cells if cell.day_index == 0]
    assert [cell.hour for cell in monday if cell.slot_start] == [9, 13, 14, 15, 16, 17, 18]
    last = [cell for cell in result.cells if cell.day_index == 0][-1]
    assert last.slot_start is False


def test_slots_never_start_in_the_past():
    week = date(2026, 9, 14)
    result = overlay([[]], _at(week, 0, 15), _week_spec(week))
    monday = [cell for cell in result.cells if cell.day_index == 0]
    assert [cell.hour for cell in monday if cell.slot_start] == [15, 16, 17, 18, 19, 20]


def test_no_participants_no_slots():
    week = date(2026, 9, 14)
    result = overlay([], _at(week, 0, 8), _week_spec(week))
    assert not any(cell.slot_start or cell.in_slot for cell in result.cells)


def test_overlapping_busy_intervals_are_merged():
    week = date(2026, 9, 14)
    busy = [BusyInterval(_at(week, 1, 10), _at(week, 1, 12)), BusyInterval(_at(week, 1, 11), _at(week, 1, 14))]
    result = overlay([busy], _at(week, 0, 8), _week_spec(week))
    tuesday = {cell.hour: cell.free_count for cell in result.cells if cell.day_index == 1}
    assert [tuesday[hour] for hour in (9, 10, 11, 12, 13, 14)] == [1, 0, 0, 0, 0, 1]


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
    assert (monday[0].hour, monday[0].minute) == (10, 0)
    assert (monday[-1].hour, monday[-1].minute) == (11, 45)


def test_validate_grid_spec_rejects_inverted_range():
    try:
        validate_grid_spec(date(2026, 9, 20), date(2026, 9, 14), "09:00", "18:00", 30, 60)
        assert False
    except ValueError:
        pass


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
