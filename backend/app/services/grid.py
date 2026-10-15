from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.domain import BusyInterval, GridSpec, OverlayResult, overlay
from app.domain import Constants as DomainConstants
from app.models import AppUser, CalendarCollection, CalendarConnection, ConnectionStatus


@dataclass(frozen=True)
class MemberInfo:
    user_id: uuid.UUID
    email: str
    calendars: int
    last_synced_at: datetime | None
    in_overlay: bool


def build_grid(
    session: Session, now: datetime, spec: GridSpec, user_ids: list[uuid.UUID]
) -> tuple[OverlayResult, list[MemberInfo]]:
    """Источник пересечения — участник: занят, если занят в любом из своих выбранных календарей.

    Участник без выбранных календарей в пересечение не входит: иначе он выглядел бы свободным всегда.
    """
    users = {user.id: user for user in session.scalars(select(AppUser).where(AppUser.id.in_(user_ids)))}
    collections = list(
        session.scalars(
            select(CalendarCollection)
            .join(CalendarConnection)
            .where(
                CalendarConnection.user_id.in_(user_ids),
                CalendarCollection.selected.is_(True),
                CalendarConnection.status.in_(
                    (ConnectionStatus.ACTIVE, ConnectionStatus.SYNCING, ConnectionStatus.PENDING)
                ),
            )
            .options(selectinload(CalendarCollection.busy_intervals), selectinload(CalendarCollection.connection))
        )
    )
    window_start = datetime.combine(spec.date_from, datetime.min.time(), tzinfo=DomainConstants.DISPLAY_TZ)
    window_end = datetime.combine(
        spec.date_to + timedelta(days=1), datetime.min.time(), tzinfo=DomainConstants.DISPLAY_TZ
    )
    per_user: dict[uuid.UUID, list[CalendarCollection]] = {user_id: [] for user_id in user_ids}
    for collection in collections:
        per_user[collection.connection.user_id].append(collection)
    sources: list[list[BusyInterval]] = []
    members: list[MemberInfo] = []
    for user_id in user_ids:
        owned = per_user.get(user_id, [])
        syncs = [item.connection.last_synced_at for item in owned if item.connection.last_synced_at]
        email = users[user_id].email if user_id in users else ""
        members.append(
            MemberInfo(
                user_id=user_id,
                email=email or "",
                calendars=len(owned),
                last_synced_at=min(syncs) if syncs and len(syncs) == len(owned) else None,
                in_overlay=bool(owned),
            )
        )
        if not owned:
            continue
        intervals: list[BusyInterval] = []
        for collection in owned:
            for row in collection.busy_intervals:
                start = row.period.lower
                end = row.period.upper
                if start < window_end and end > window_start:
                    intervals.append(BusyInterval(start=start, end=end))
        sources.append(intervals)
    return overlay(sources, now, spec), members


def list_selected_sources(session: Session, user_id: uuid.UUID) -> list[dict]:
    rows = session.scalars(
        select(CalendarCollection)
        .join(CalendarConnection)
        .where(CalendarConnection.user_id == user_id)
        .options(selectinload(CalendarCollection.connection))
        .order_by(CalendarCollection.display_name)
    )
    return [
        {
            "id": str(item.id),
            "connection_id": str(item.connection_id),
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
