from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.adapters import apple, google, link, yandex
from app.adapters.caldav_client import CalDavAuthError
from app.models import (
    AuthKind,
    BusyIntervalRow,
    CalendarCollection,
    CalendarConnection,
    ConnectionStatus,
    Provider,
)
from app.security import secret_box
from app.services import cache
from sqlalchemy.dialects.postgresql import Range


def list_connections(session: Session, user_id: uuid.UUID) -> list[CalendarConnection]:
    return list(
        session.scalars(
            select(CalendarConnection)
            .where(CalendarConnection.user_id == user_id)
            .options(selectinload(CalendarConnection.collections))
            .order_by(CalendarConnection.created_at)
        )
    )


def get_connection(session: Session, connection_id: uuid.UUID, user_id: uuid.UUID | None = None) -> CalendarConnection:
    query = select(CalendarConnection).where(CalendarConnection.id == connection_id)
    if user_id is not None:
        query = query.where(CalendarConnection.user_id == user_id)
    connection = session.scalars(query.options(selectinload(CalendarConnection.collections))).first()
    if connection is None:
        raise KeyError("connection")
    return connection


def create_oauth_connection(session: Session, user_id: uuid.UUID, provider: str, secret: dict, email: str | None) -> CalendarConnection:
    connection = CalendarConnection(
        user_id=user_id,
        provider=provider,
        auth_kind=AuthKind.OAUTH,
        status=ConnectionStatus.PENDING,
        encrypted_secret=secret_box.encrypt(secret),
        account_email=email,
    )
    session.add(connection)
    session.flush()
    try:
        _discover_into(session, connection, secret)
    except Exception as error:
        connection.status = ConnectionStatus.AUTH_FAILED
        connection.last_error = str(error)
    session.refresh(connection, attribute_names=["collections"])
    return connection


def create_apple_connection(session: Session, user_id: uuid.UUID, email: str, app_password: str) -> CalendarConnection:
    secret = {"email": email, "app_password": app_password}
    connection = CalendarConnection(
        user_id=user_id,
        provider=Provider.APPLE,
        auth_kind=AuthKind.APP_PASSWORD,
        status=ConnectionStatus.PENDING,
        encrypted_secret=secret_box.encrypt(secret),
        account_email=email,
    )
    session.add(connection)
    session.flush()
    try:
        _discover_into(session, connection, secret)
    except CalDavAuthError as error:
        connection.status = ConnectionStatus.AUTH_FAILED
        connection.last_error = str(error)
        raise
    session.refresh(connection, attribute_names=["collections"])
    return connection


def create_link_connection(session: Session, user_id: uuid.UUID, url: str) -> CalendarConnection:
    normalized = link.normalize_url(url)
    link.validate(normalized)
    connection = CalendarConnection(
        user_id=user_id,
        provider=Provider.LINK,
        auth_kind=AuthKind.PUBLIC_LINK,
        status=ConnectionStatus.ACTIVE,
        encrypted_secret=secret_box.encrypt({"url": normalized}),
    )
    connection.collections.append(
        CalendarCollection(external_id=Constants.LINK_COLLECTION_ID, display_name=link.title_for(normalized), selected=True)
    )
    session.add(connection)
    session.flush()
    cache.bump_user(user_id)
    return connection


def select_collections(
    session: Session, connection_id: uuid.UUID, selected_ids: list[uuid.UUID], user_id: uuid.UUID
) -> CalendarConnection:
    connection = get_connection(session, connection_id, user_id)
    selected = set(selected_ids)
    for collection in connection.collections:
        collection.selected = collection.id in selected
    connection.status = ConnectionStatus.ACTIVE
    session.flush()
    cache.bump_user(connection.user_id)
    return connection


def delete_connection(session: Session, connection_id: uuid.UUID, user_id: uuid.UUID) -> None:
    connection = get_connection(session, connection_id, user_id)
    session.delete(connection)
    session.flush()
    cache.bump_user(user_id)


def save_secret(session: Session, connection: CalendarConnection, secret: dict) -> None:
    connection.encrypted_secret = secret_box.encrypt(secret)


def load_secret(connection: CalendarConnection) -> dict:
    return secret_box.decrypt(connection.encrypted_secret)


def refresh_if_needed(session: Session, connection: CalendarConnection, secret: dict) -> dict:
    expires_at = secret.get("expires_at")
    refresh_token = secret.get("refresh_token")
    if not expires_at or not refresh_token:
        return secret
    moment = datetime.fromisoformat(expires_at)
    if moment - timedelta(seconds=Constants.REFRESH_SKEW_SECONDS) > datetime.now(timezone.utc):
        return secret
    if connection.provider == Provider.GOOGLE:
        payload = google.refresh_access(refresh_token)
    elif connection.provider == Provider.YANDEX:
        payload = yandex.refresh_access(refresh_token)
    else:
        return secret
    secret["access_token"] = payload["access_token"]
    if payload.get("refresh_token"):
        secret["refresh_token"] = payload["refresh_token"]
    if payload.get("expires_in"):
        secret["expires_at"] = (
            datetime.now(timezone.utc) + timedelta(seconds=int(payload["expires_in"]))
        ).isoformat()
    save_secret(session, connection, secret)
    return secret


def replace_busy_window(
    session: Session,
    collection: CalendarCollection,
    window_start: datetime,
    window_end: datetime,
    occurrences,
) -> None:
    window = Range(window_start, window_end, bounds="[)")
    session.execute(
        delete(BusyIntervalRow).where(
            BusyIntervalRow.collection_id == collection.id,
            BusyIntervalRow.period.op("&&")(window),
        )
    )
    session.flush()
    seen: set[tuple[str, datetime]] = set()
    for item in occurrences:
        start = item.start.astimezone(timezone.utc)
        end = item.end.astimezone(timezone.utc)
        key = (item.uid, start)
        if key in seen:
            continue
        seen.add(key)
        session.add(
            BusyIntervalRow(
                collection_id=collection.id,
                uid=item.uid[:1024],
                occurrence_start=start,
                period=Range(start, end, bounds="[)"),
                source="auto",
            )
        )
    session.flush()


def _discover_into(session: Session, connection: CalendarConnection, secret: dict) -> None:
    if connection.provider == Provider.GOOGLE:
        calendars = google.discover(secret)
    elif connection.provider == Provider.YANDEX:
        calendars = yandex.discover(secret)
    else:
        calendars = apple.discover(secret)
        if calendars:
            connection.principal_url = calendars[0].external_id
    for item in calendars:
        connection.collections.append(
            CalendarCollection(
                external_id=item.external_id,
                display_name=item.display_name,
                selected=item.selected_by_default,
            )
        )
    connection.status = ConnectionStatus.PENDING
    session.flush()


class Constants:
    REFRESH_SKEW_SECONDS = 120
    LINK_COLLECTION_ID = "ics"
