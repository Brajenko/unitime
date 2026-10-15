from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class BusyInterval:
    start: datetime
    end: datetime


@dataclass(frozen=True)
class GridSpec:
    date_from: date
    date_to: date
    time_start: time
    time_end: time
    step_minutes: int
    slot_minutes: int


@dataclass(frozen=True)
class GridCell:
    start: datetime
    end: datetime
    free_count: int
    total: int
    day_index: int
    hour: int
    minute: int
    day: str
    slot_start: bool = False
    in_slot: bool = False


@dataclass(frozen=True)
class OverlayResult:
    cells: list[GridCell]
    total: int


def overlay(
    sources: list[list[BusyInterval]],
    now: datetime,
    spec: GridSpec | None = None,
) -> OverlayResult:
    """Сетка занятости. Источник — участник: он занят, если занят в любом из своих календарей.

    Слот длины `slot_minutes` может начинаться в клетке (`slot_start`), если эта клетка и
    следующие подряд в тот же день свободны у всех и начинаются не раньше `now`.
    `in_slot` — клетка входит хотя бы в один возможный слот.
    """
    window = spec or default_grid_spec(now.date())
    total = len(sources)
    merged = [_merge(intervals) for intervals in sources]
    step = timedelta(minutes=window.step_minutes)
    day_count = (window.date_to - window.date_from).days + 1
    cells: list[GridCell] = []
    for day_index in range(day_count):
        day = window.date_from + timedelta(days=day_index)
        cursor = datetime.combine(day, window.time_start, tzinfo=Constants.DISPLAY_TZ)
        day_end = datetime.combine(day, window.time_end, tzinfo=Constants.DISPLAY_TZ)
        while cursor + step <= day_end:
            end = cursor + step
            free_count = sum(1 for intervals in merged if not _overlaps(intervals, cursor, end))
            cells.append(
                GridCell(
                    start=cursor,
                    end=end,
                    free_count=free_count,
                    total=total,
                    day_index=day_index,
                    hour=cursor.hour,
                    minute=cursor.minute,
                    day=day.isoformat(),
                )
            )
            cursor = end
    return OverlayResult(cells=_mark_slots(cells, now, window), total=total)


def monday_of(day: date) -> date:
    return day - timedelta(days=day.weekday())


def default_grid_spec(today: date) -> GridSpec:
    return GridSpec(
        date_from=today,
        date_to=today + timedelta(days=Constants.DEFAULT_RANGE_DAYS - 1),
        time_start=time(Constants.GRID_HOUR_START),
        time_end=time(Constants.GRID_HOUR_END),
        step_minutes=Constants.DEFAULT_STEP_MINUTES,
        slot_minutes=Constants.DEFAULT_SLOT_MINUTES,
    )


def parse_clock(value: str) -> time:
    parts = value.split(":")
    return time(int(parts[0]), int(parts[1]))


def validate_grid_spec(
    date_from: date,
    date_to: date,
    time_from: str,
    time_to: str,
    step_minutes: int,
    slot_minutes: int,
) -> GridSpec:
    if step_minutes not in Constants.STEP_MINUTES:
        raise ValueError("Шаг сетки должен быть от 15 минут до 2 часов")
    if slot_minutes not in Constants.SLOT_MINUTES:
        raise ValueError("Длительность слота задана неверно")
    if slot_minutes < step_minutes or slot_minutes % step_minutes != 0:
        raise ValueError("Длительность слота должна быть кратна шагу сетки")
    if date_to < date_from:
        raise ValueError("Дата начала должна быть не позже даты конца")
    span = (date_to - date_from).days + 1
    if span > Constants.MAX_RANGE_DAYS:
        raise ValueError(f"Диапазон дат не больше {Constants.MAX_RANGE_DAYS} дней")
    start = parse_clock(time_from)
    end = parse_clock(time_to)
    if start >= end:
        raise ValueError("Время начала сетки должно быть раньше конца")
    last = datetime.combine(date(2000, 1, 1), start) + timedelta(minutes=step_minutes)
    limit = datetime.combine(date(2000, 1, 1), end)
    if last > limit:
        raise ValueError("Шаг больше выбранного окна времени")
    if datetime.combine(date(2000, 1, 1), start) + timedelta(minutes=slot_minutes) > limit:
        raise ValueError("Слот длиннее выбранного окна времени")
    return GridSpec(
        date_from=date_from,
        date_to=date_to,
        time_start=start,
        time_end=end,
        step_minutes=step_minutes,
        slot_minutes=slot_minutes,
    )


def _merge(intervals: list[BusyInterval]) -> list[tuple[datetime, datetime]]:
    merged: list[tuple[datetime, datetime]] = []
    for item in sorted(intervals, key=lambda value: value.start):
        if item.end <= item.start:
            continue
        if merged and item.start <= merged[-1][1]:
            if item.end > merged[-1][1]:
                merged[-1] = (merged[-1][0], item.end)
        else:
            merged.append((item.start, item.end))
    return merged


def _overlaps(merged: list[tuple[datetime, datetime]], start: datetime, end: datetime) -> bool:
    # последний интервал, начавшийся до конца клетки; интервалы не пересекаются и отсортированы
    lo, hi = 0, len(merged)
    while lo < hi:
        mid = (lo + hi) // 2
        if merged[mid][0] < end:
            lo = mid + 1
        else:
            hi = mid
    return lo > 0 and merged[lo - 1][1] > start


def _mark_slots(cells: list[GridCell], now: datetime, spec: GridSpec) -> list[GridCell]:
    if not cells or cells[0].total == 0:
        return cells
    length = spec.slot_minutes // spec.step_minutes
    if length < 1 or spec.slot_minutes % spec.step_minutes != 0:
        return cells
    usable = [cell.free_count == cell.total and cell.start >= now for cell in cells]
    starts = [False] * len(cells)
    for index in range(len(cells) - length + 1):
        if all(
            usable[index + offset]
            and cells[index + offset].day_index == cells[index].day_index
            and (offset == 0 or cells[index + offset].start == cells[index + offset - 1].end)
            for offset in range(length)
        ):
            starts[index] = True
    covered = [False] * len(cells)
    for index, is_start in enumerate(starts):
        if is_start:
            for offset in range(length):
                covered[index + offset] = True
    return [
        replace(cell, slot_start=starts[index], in_slot=covered[index]) for index, cell in enumerate(cells)
    ]


class Constants:
    DISPLAY_TZ = ZoneInfo("Europe/Moscow")
    DAYS_IN_WEEK = 7
    DEFAULT_RANGE_DAYS = 7
    MAX_RANGE_DAYS = 14
    GRID_HOUR_START = 9
    GRID_HOUR_END = 21
    DEFAULT_STEP_MINUTES = 60
    DEFAULT_SLOT_MINUTES = 60
    STEP_MINUTES = (15, 30, 45, 60, 90, 120)
    SLOT_MINUTES = (15, 30, 45, 60, 90, 120, 180)
