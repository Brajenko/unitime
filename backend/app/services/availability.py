from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import Range
from sqlalchemy.orm import Session

from app.domain import BusyInterval, merge_intervals
from app.models import AvailabilityWindow
from app.services import cache


def validate_windows(windows: list[BusyInterval], range_start: datetime, range_end: datetime) -> None:
    if len(windows) > Constants.MAX_WINDOWS:
        raise ValueError(f"Не больше {Constants.MAX_WINDOWS} окон за раз")
    for item in windows:
        if item.start.tzinfo is None or item.end.tzinfo is None:
            raise ValueError("Время должно быть с часовым поясом")
        if item.end <= item.start:
            raise ValueError("Конец окна должен быть позже начала")
        if item.start < range_start or item.end > range_end:
            raise ValueError("Окно выходит за выбранный диапазон дат")
        for value in (item.start, item.end):
            if value.second or value.microsecond or value.minute % Constants.MINUTE_STEP:
                raise ValueError("Время должно быть кратно 5 минутам")


def replace_availability(
    session: Session,
    user_id: uuid.UUID,
    range_start: datetime,
    range_end: datetime,
    windows: list[BusyInterval],
) -> list[BusyInterval]:
    validate_windows(windows, range_start, range_end)
    session.execute(
        delete(AvailabilityWindow).where(
            AvailabilityWindow.user_id == user_id,
            AvailabilityWindow.period.op("&&")(Range(range_start, range_end, bounds="[)")),
        )
    )
    merged = merge_intervals(windows)
    for item in merged:
        session.add(AvailabilityWindow(user_id=user_id, period=Range(item.start, item.end, bounds="[)")))
    session.flush()
    cache.bump_user(user_id)
    return merged


def list_availability(
    session: Session, user_id: uuid.UUID, range_start: datetime, range_end: datetime
) -> list[BusyInterval]:
    return windows_by_user(session, [user_id], range_start, range_end).get(user_id, [])


def windows_by_user(
    session: Session, user_ids: list[uuid.UUID], range_start: datetime, range_end: datetime
) -> dict[uuid.UUID, list[BusyInterval]]:
    rows = session.scalars(
        select(AvailabilityWindow).where(
            AvailabilityWindow.user_id.in_(user_ids),
            AvailabilityWindow.period.op("&&")(Range(range_start, range_end, bounds="[)")),
        )
    )
    result: dict[uuid.UUID, list[BusyInterval]] = {}
    for row in rows:
        result.setdefault(row.user_id, []).append(BusyInterval(start=row.period.lower, end=row.period.upper))
    for items in result.values():
        items.sort(key=lambda item: item.start)
    return result


def users_with_availability(session: Session, user_ids: list[uuid.UUID]) -> set[uuid.UUID]:
    """Кто в ручном режиме: отметил хотя бы одно окно (в любой неделе)."""
    return set(
        session.scalars(select(AvailabilityWindow.user_id).where(AvailabilityWindow.user_id.in_(user_ids)).distinct())
    )


class Constants:
    MAX_WINDOWS = 500
    MINUTE_STEP = 5
