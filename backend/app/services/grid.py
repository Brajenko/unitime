from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.domain import BusyInterval, GridSpec, OverlayResult, overlay
from app.domain import Constants as DomainConstants
from app.models import CalendarCollection, CalendarConnection, ConnectionStatus
from app.services.connections import DEMO_USER_ID


def build_grid(session: Session, now: datetime, spec: GridSpec) -> OverlayResult:
    collections = list(
        session.scalars(
            select(CalendarCollection)
            .join(CalendarConnection)
            .where(
                CalendarConnection.user_id == DEMO_USER_ID,
                CalendarCollection.selected.is_(True),
                CalendarConnection.status.in_(
                    (ConnectionStatus.ACTIVE, ConnectionStatus.SYNCING, ConnectionStatus.PENDING)
                ),
            )
            .options(selectinload(CalendarCollection.busy_intervals))
        )
    )
    window_start = datetime.combine(spec.date_from, datetime.min.time(), tzinfo=DomainConstants.DISPLAY_TZ)
    window_end = datetime.combine(spec.date_to + timedelta(days=1), datetime.min.time(), tzinfo=DomainConstants.DISPLAY_TZ)
    sources: list[list[BusyInterval]] = []
    for collection in collections:
        intervals: list[BusyInterval] = []
        for row in collection.busy_intervals:
            start = row.period.lower
            end = row.period.upper
            if start < window_end and end > window_start:
                intervals.append(BusyInterval(start=start, end=end))
        sources.append(intervals)
    return overlay(sources, now, spec)


def list_selected_sources(session: Session) -> list[dict]:
    rows = session.scalars(
        select(CalendarCollection)
        .join(CalendarConnection)
        .where(CalendarConnection.user_id == DEMO_USER_ID)
        .options(selectinload(CalendarCollection.connection))
        .order_by(CalendarCollection.display_name)
    )
    return [
        {
            "id": str(item.id),
            "name": item.display_name,
            "provider": item.connection.provider,
            "selected": item.selected,
            "status": item.connection.status,
            "account_email": item.connection.account_email,
            "last_error": item.connection.last_error,
        }
        for item in rows
        if item.selected
    ]
