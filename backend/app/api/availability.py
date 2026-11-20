from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.db import get_db
from app.domain import BusyInterval
from app.domain import Constants as DomainConstants
from app.models import AppUser
from app.schemas import AvailabilityIn, AvailabilityWindowIO
from app.services import availability

router = APIRouter()


def _range(date_from: str, date_to: str, tz: str) -> tuple[datetime, datetime, ZoneInfo]:
    """Диапазон целых дней [date_from 00:00, date_to+1 00:00) в поясе tz."""
    try:
        zone = ZoneInfo(tz)
    except (KeyError, ValueError) as error:
        raise HTTPException(status_code=400, detail="Неизвестный часовой пояс") from error
    try:
        start_day = date.fromisoformat(date_from)
        end_day = date.fromisoformat(date_to)
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Даты в формате ГГГГ-ММ-ДД") from error
    if end_day < start_day or (end_day - start_day).days + 1 > DomainConstants.MAX_RANGE_DAYS:
        raise HTTPException(status_code=400, detail=f"Диапазон от 1 до {DomainConstants.MAX_RANGE_DAYS} дней")
    start = datetime.combine(start_day, datetime.min.time(), tzinfo=zone)
    end = datetime.combine(end_day + timedelta(days=1), datetime.min.time(), tzinfo=zone)
    return start, end, zone


def _serialize(items: list[BusyInterval], zone: ZoneInfo) -> list[AvailabilityWindowIO]:
    return [AvailabilityWindowIO(start=item.start.astimezone(zone), end=item.end.astimezone(zone)) for item in items]


@router.get("/me/availability", response_model=list[AvailabilityWindowIO])
def get_availability(
    date_from: str,
    date_to: str,
    tz: str = Query(default=DomainConstants.DISPLAY_TZ.key),
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    start, end, zone = _range(date_from, date_to, tz)
    return _serialize(availability.list_availability(db, user.id, start, end), zone)


@router.put("/me/availability", response_model=list[AvailabilityWindowIO])
def put_availability(
    body: AvailabilityIn,
    date_from: str,
    date_to: str,
    tz: str = Query(default=DomainConstants.DISPLAY_TZ.key),
    user: AppUser = Depends(current_user),
    db: Session = Depends(get_db),
):
    start, end, zone = _range(date_from, date_to, tz)
    windows = [BusyInterval(start=item.start, end=item.end) for item in body.windows]
    try:
        saved = availability.replace_availability(db, user.id, start, end, windows)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return _serialize(saved, zone)
