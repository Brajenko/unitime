from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True)
class SuggestedSlot:
    start: datetime
    end: datetime


@dataclass(frozen=True)
class OverlayResult:
    cells: list[GridCell]
    slots: list[SuggestedSlot]
    total: int

    @property
    def suggested(self) -> SuggestedSlot | None:
        if not self.slots:
            return None
        return self.slots[0]


def overlay(
    sources: list[list[BusyInterval]],
    now: datetime,
    spec: GridSpec | None = None,
) -> OverlayResult:
    window = spec or default_grid_spec(now.date())
    total = len(sources)
    cells: list[GridCell] = []
    step = timedelta(minutes=window.step_minutes)
    day_count = (window.date_to - window.date_from).days + 1
    for day_index in range(day_count):
        day = window.date_from + timedelta(days=day_index)
        cursor = datetime.combine(day, window.time_start, tzinfo=Constants.DISPLAY_TZ)
        day_end = datetime.combine(day, window.time_end, tzinfo=Constants.DISPLAY_TZ)
        while cursor + step <= day_end:
            end = cursor + step
            free_count = sum(1 for intervals in sources if not _overlaps_any(intervals, cursor, end))
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
    slots = suggest_slots(cells, total, now, window)
    return OverlayResult(cells=cells, slots=slots, total=total)


def suggest_slot(
    cells: list[GridCell],
    total: int,
    now: datetime,
    spec: GridSpec | None = None,
) -> SuggestedSlot | None:
    found = suggest_slots(cells, total, now, spec)
    if not found:
        return None
    return found[0]


def suggest_slots(
    cells: list[GridCell],
    total: int,
    now: datetime,
    spec: GridSpec | None = None,
) -> list[SuggestedSlot]:
    if total == 0:
        return []
    window = spec or default_grid_spec(now.date())
    length = window.slot_minutes // window.step_minutes
    if length < 1 or window.slot_minutes % window.step_minutes != 0:
        return []
    ranked: list[tuple[float, SuggestedSlot]] = []
    for run in _same_day_runs(cells, total):
        if len(run) < length:
            continue
        best_piece: list[GridCell] | None = None
        best_score: float | None = None
        for index in range(len(run) - length + 1):
            piece = run[index : index + length]
            score = _score_window(piece, now, window)
            if best_score is None or score > best_score:
                best_score = score
                best_piece = piece
        if best_piece is not None and best_score is not None:
            ranked.append((best_score, SuggestedSlot(start=best_piece[0].start, end=best_piece[-1].end)))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in ranked]


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


def _overlaps_any(intervals: list[BusyInterval], start: datetime, end: datetime) -> bool:
    return any(item.start < end and item.end > start for item in intervals)


def _same_day_runs(cells: list[GridCell], total: int) -> list[list[GridCell]]:
    runs: list[list[GridCell]] = []
    current: list[GridCell] = []
    for cell in cells:
        can_extend = (
            cell.free_count == total
            and current
            and cell.start == current[-1].end
            and cell.day_index == current[-1].day_index
        )
        if can_extend:
            current.append(cell)
            continue
        if current:
            runs.append(current)
            current = []
        if cell.free_count == total:
            current = [cell]
    if current:
        runs.append(current)
    return runs


def _score_window(window: list[GridCell], now: datetime, spec: GridSpec) -> float:
    start = window[0].start
    hours = (window[-1].end - window[0].start).total_seconds() / Constants.SECONDS_IN_HOUR
    rounded = int(round(hours))
    if abs(hours - rounded) < Constants.HOUR_EPS and rounded in Constants.LENGTH_SCORES:
        length_score = Constants.LENGTH_SCORES[rounded]
    else:
        length_score = hours
    weekday_score = Constants.WEEKDAY_BONUS if start.weekday() < 5 else 0.0
    end_minutes = spec.time_end.hour * Constants.MINUTES_IN_HOUR + spec.time_end.minute
    start_minutes = start.hour * Constants.MINUTES_IN_HOUR + start.minute
    early_score = float(end_minutes - start_minutes) / Constants.MINUTES_IN_HOUR
    local_now = now.astimezone(Constants.DISPLAY_TZ)
    hours_apart = abs((start - local_now).total_seconds()) / Constants.SECONDS_IN_HOUR
    proximity = -hours_apart * Constants.PROXIMITY_WEIGHT
    return (
        length_score * Constants.LENGTH_WEIGHT
        + weekday_score * Constants.WEEKDAY_WEIGHT
        + early_score
        + proximity
    )


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
    LENGTH_SCORES = {1: 1.0, 2: 2.2, 3: 3.0}
    LENGTH_WEIGHT = 100.0
    WEEKDAY_BONUS = 10.0
    WEEKDAY_WEIGHT = 10.0
    PROXIMITY_WEIGHT = 0.1
    SECONDS_IN_HOUR = 3600.0
    MINUTES_IN_HOUR = 60
    HOUR_EPS = 0.01
