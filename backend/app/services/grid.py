from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.domain import BusyInterval, GridSpec, OverlayResult, free_to_busy, overlay
from app.services.availability import users_with_availability, windows_by_user
from app.models import AppUser, CalendarCollection, CalendarConnection, ConnectionStatus


@dataclass(frozen=True)
class MemberInfo:
    user_id: uuid.UUID
    email: str
    calendars: int
    last_synced_at: datetime | None
    in_overlay: bool
    status: str


def build_grid(
    session: Session, now: datetime, spec: GridSpec, user_ids: list[uuid.UUID]
) -> tuple[OverlayResult, list[MemberInfo]]:
    """Источник пересечения — участник: занят, если занят в любом из своих выбранных календарей.

    Участник без календарей, но с ручными свободными окнами (US-07), занят всё время вне этих окон.
    Календарь главнее: при подключённом календаре ручные окна не учитываются.
    Участник без календарей и без ручных окон в пересечение не входит: иначе он выглядел бы свободным всегда.
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
    window_start = datetime.combine(spec.date_from, datetime.min.time(), tzinfo=spec.tz)
    window_end = datetime.combine(spec.date_to + timedelta(days=1), datetime.min.time(), tzinfo=spec.tz)
    failed_users = set(
        session.scalars(
            select(CalendarConnection.user_id).where(
                CalendarConnection.user_id.in_(user_ids),
                CalendarConnection.status == ConnectionStatus.AUTH_FAILED,
            )
        )
    )
    per_user: dict[uuid.UUID, list[CalendarCollection]] = {user_id: [] for user_id in user_ids}
    for collection in collections:
        per_user[collection.connection.user_id].append(collection)
    manual_candidates = [user_id for user_id in user_ids if not per_user.get(user_id)]
    manual_users = users_with_availability(session, manual_candidates) if manual_candidates else set()
    manual_windows = windows_by_user(session, list(manual_users), window_start, window_end) if manual_users else {}
    sources: list[list[BusyInterval]] = []
    coverage: list[list[BusyInterval] | None] = []
    members: list[MemberInfo] = []
    for user_id in user_ids:
        owned = per_user.get(user_id, [])
        syncs = [item.connection.last_synced_at for item in owned if item.connection.last_synced_at]
        email = users[user_id].email if user_id in users else ""
        last_synced_at = min(syncs) if syncs and len(syncs) == len(owned) else None
        members.append(
            MemberInfo(
                user_id=user_id,
                email=email or "",
                calendars=len(owned),
                last_synced_at=last_synced_at,
                in_overlay=bool(owned) or user_id in manual_users,
                status=member_status(
                    bool(owned), user_id in failed_users, last_synced_at, now, has_manual=user_id in manual_users
                ),
            )
        )
        if not owned:
            if user_id in manual_users:
                windows = manual_windows.get(user_id, [])
                sources.append(free_to_busy(windows, window_start, window_end))
                coverage.append(marked_days(windows, spec.tz))
            continue
        intervals: list[BusyInterval] = []
        for collection in owned:
            for row in collection.busy_intervals:
                start = row.period.lower
                end = row.period.upper
                if start < window_end and end > window_start:
                    intervals.append(BusyInterval(start=start, end=end))
        sources.append(intervals)
        coverage.append(None)
    return overlay(sources, now, spec, coverage), members


def marked_days(windows: list[BusyInterval], tz) -> list[BusyInterval]:
    """Дни (в поясе сетки), где участник отметил хоть одно окно: только в них он учитывается."""
    days: set = set()
    for item in windows:
        day = item.start.astimezone(tz).date()
        last = (item.end - timedelta(microseconds=1)).astimezone(tz).date()
        while day <= last:
            days.add(day)
            day += timedelta(days=1)
    return [
        BusyInterval(
            start=datetime.combine(day, datetime.min.time(), tzinfo=tz),
            end=datetime.combine(day + timedelta(days=1), datetime.min.time(), tzinfo=tz),
        )
        for day in sorted(days)
    ]


def member_status(
    has_calendars: bool,
    has_failed: bool,
    last_synced_at: datetime | None,
    now: datetime,
    has_manual: bool = False,
) -> str:
    """ok / manual / no_calendars / auth_failed / stale: что показать капитану про участника."""
    if not has_calendars:
        if has_manual:
            return "manual"
        return "auth_failed" if has_failed else "no_calendars"
    if last_synced_at is None or now - last_synced_at > timedelta(minutes=Constants.STALE_MINUTES):
        return "stale"
    return "ok"


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


class Constants:
    STALE_MINUTES = 30
