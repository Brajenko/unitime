from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.adapters import google, yandex
from app.adapters.google import GoogleOAuthNotConfigured
from app.adapters.yandex import YandexOAuthNotConfigured
from app.config import settings
from app.db import get_db
from app.domain import Constants as DomainConstants
from app.models import Provider
from app.schemas import AppleConnectIn, ConnectionOut, SelectCollectionsIn
from app.services import oauth_state
from app.services.connections import (
    create_apple_connection,
    create_oauth_connection,
    get_connection,
    list_connections,
    select_collections,
)
from app.sync.tasks import sync_connection_task

router = APIRouter()


def _serialize(connection) -> ConnectionOut:
    return ConnectionOut(
        id=str(connection.id),
        provider=connection.provider,
        status=connection.status,
        account_email=connection.account_email,
        last_error=connection.last_error,
        collections=[
            {"id": str(item.id), "name": item.display_name, "selected": item.selected}
            for item in connection.collections
        ],
    )


@router.get("/providers")
def providers():
    return [
        {"id": Provider.GOOGLE, "name": "Google", "oauth": True},
        {"id": Provider.YANDEX, "name": "Яндекс", "oauth": True},
        {"id": Provider.APPLE, "name": "Apple", "oauth": False},
    ]


@router.get("/connections", response_model=list[ConnectionOut])
def connections(db: Session = Depends(get_db)):
    return [_serialize(item) for item in list_connections(db)]


@router.get("/connections/{connection_id}", response_model=ConnectionOut)
def connection_detail(connection_id: uuid.UUID, db: Session = Depends(get_db)):
    try:
        return _serialize(get_connection(db, connection_id))
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Подключение не найдено") from error


@router.get("/connections/google/start")
def google_start():
    try:
        url = google.authorization_url(oauth_state.put_state(Provider.GOOGLE))
    except GoogleOAuthNotConfigured:
        return RedirectResponse(f"{settings.public_url}/connect?error=google_config")
    return RedirectResponse(url)


@router.get("/connections/yandex/start")
def yandex_start():
    try:
        url = yandex.authorization_url(oauth_state.put_state(Provider.YANDEX))
    except YandexOAuthNotConfigured:
        return RedirectResponse(f"{settings.public_url}/connect?error=yandex_config")
    return RedirectResponse(url)


@router.get("/auth/google/callback")
def google_callback(code: str | None = None, state: str | None = None, error: str | None = None, db: Session = Depends(get_db)):
    return _oauth_callback(Provider.GOOGLE, code, state, error, db, google.exchange_code)


@router.get("/auth/yandex/callback")
def yandex_callback(code: str | None = None, state: str | None = None, error: str | None = None, db: Session = Depends(get_db)):
    return _oauth_callback(Provider.YANDEX, code, state, error, db, yandex.exchange_code)


@router.post("/connections/apple", response_model=ConnectionOut)
def apple_connect(body: AppleConnectIn, db: Session = Depends(get_db)):
    try:
        connection = create_apple_connection(db, body.email.strip(), body.app_password.strip())
    except Exception as error:
        raise HTTPException(status_code=401, detail="Не удалось войти в iCloud. Проверьте email и пароль приложения.") from error
    return _serialize(connection)


@router.patch("/connections/{connection_id}/collections", response_model=ConnectionOut)
def patch_collections(connection_id: uuid.UUID, body: SelectCollectionsIn, db: Session = Depends(get_db)):
    try:
        ids = [uuid.UUID(item) for item in body.selected_ids]
        connection = select_collections(db, connection_id, ids)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Подключение не найдено") from error
    return _serialize(connection)


@router.post("/connections/{connection_id}/sync")
def enqueue_sync(
    connection_id: uuid.UUID,
    date_from: str | None = Query(default=None),
    date_to: str | None = Query(default=None),
    db: Session = Depends(get_db),
):
    try:
        get_connection(db, connection_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail="Подключение не найдено") from error
    today = datetime.now(DomainConstants.DISPLAY_TZ).date()
    start = date_from or today.isoformat()
    end = date_to or (date.fromisoformat(start) + timedelta(days=DomainConstants.DEFAULT_RANGE_DAYS - 1)).isoformat()
    sync_connection_task.delay(str(connection_id), start, end)
    return {"ok": True}


def _oauth_callback(provider: str, code: str | None, state: str | None, error: str | None, db, exchange) -> RedirectResponse:
    frontend = f"{settings.public_url}/connect"
    if error or not code or not state:
        return RedirectResponse(f"{frontend}?error=oauth")
    payload_state = oauth_state.pop_state(state)
    if payload_state is None or payload_state.get("provider") != provider:
        return RedirectResponse(f"{frontend}?error=state")
    try:
        token = exchange(code)
    except Exception:
        return RedirectResponse(f"{frontend}?error=token")
    secret = {
        "access_token": token["access_token"],
        "refresh_token": token.get("refresh_token"),
        "email": token.get("email"),
    }
    if token.get("expires_in"):
        secret["expires_at"] = (
            datetime.now(timezone.utc) + timedelta(seconds=int(token["expires_in"]))
        ).isoformat()
    connection = create_oauth_connection(db, provider, secret, token.get("email"))
    return RedirectResponse(f"{frontend}?connection_id={connection.id}&step=select")
