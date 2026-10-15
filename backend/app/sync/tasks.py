from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta

import httpx
from httpx import HTTPStatusError
from sqlalchemy import select

from app.adapters import apple, google, link, yandex
from app.adapters.caldav_client import CalDavAuthError
from celery.signals import worker_ready

from app.celery_app import celery_app
from app.db import SessionLocal
from app.domain import Constants as DomainConstants
from app.models import CalendarConnection, ConnectionStatus, Provider
from app.services import cache
from app.services.connections import get_connection, load_secret, refresh_if_needed, replace_busy_window

logger = logging.getLogger(__name__)


@celery_app.task(name="sync_connection", bind=True)
def sync_connection_task(self, connection_id: str, date_from: str, date_to: str) -> None:
    session = SessionLocal()
    try:
        connection = get_connection(session, uuid.UUID(connection_id))
        connection.status = ConnectionStatus.SYNCING
        connection.last_error = None
        session.commit()
        cache.bump_user(connection.user_id)
        secret = refresh_if_needed(session, connection, load_secret(connection))
        start = date.fromisoformat(date_from)
        end = date.fromisoformat(date_to)
        window_start = datetime.combine(start, datetime.min.time(), tzinfo=DomainConstants.DISPLAY_TZ)
        window_end = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=DomainConstants.DISPLAY_TZ)
        for collection in connection.collections:
            if not collection.selected:
                continue
            occurrences = _fetch(connection.provider, secret, collection.external_id, window_start, window_end)
            replace_busy_window(session, collection, window_start, window_end, occurrences)
        connection.status = ConnectionStatus.ACTIVE
        connection.last_synced_at = datetime.now(tz=DomainConstants.DISPLAY_TZ)
        session.commit()
        cache.bump_user(connection.user_id)
    except link.LinkError as error:
        session.rollback()
        _mark_failed(session, connection_id, str(error), auth_failed=True)
    except (CalDavAuthError, HTTPStatusError) as error:
        session.rollback()
        if _is_transient(error):
            _mark_failed(session, connection_id, "Провайдер временно недоступен", auth_failed=False)
            raise self.retry(exc=error, countdown=backoff_seconds(self.request.retries), max_retries=Constants.MAX_RETRIES)
        _mark_failed(session, connection_id, str(error), auth_failed=True)
    except Exception as error:
        logger.exception("sync failed for %s", connection_id)
        session.rollback()
        _mark_failed(session, connection_id, "Не удалось обновить календарь", auth_failed=False)
        raise self.retry(exc=error, countdown=backoff_seconds(self.request.retries), max_retries=Constants.MAX_RETRIES)
    finally:
        session.close()


def _fetch(provider: str, secret: dict, external_id: str, window_start: datetime, window_end: datetime):
    if provider == Provider.GOOGLE:
        return google.fetch_busy(secret, external_id, window_start, window_end)
    if provider == Provider.YANDEX:
        return yandex.fetch_busy(secret, external_id, window_start, window_end)
    if provider == Provider.LINK:
        return link.fetch_busy(secret, external_id, window_start, window_end)
    return apple.fetch_busy(secret, external_id, window_start, window_end)


def _mark_failed(session, connection_id: str, message: str, auth_failed: bool) -> None:
    try:
        connection = get_connection(session, uuid.UUID(connection_id))
        connection.status = ConnectionStatus.AUTH_FAILED if auth_failed else ConnectionStatus.ACTIVE
        connection.last_error = message[:2000]
        session.commit()
        cache.bump_user(connection.user_id)
    except Exception:
        session.rollback()


@celery_app.task(name="sync_all_connections")
def sync_all_connections_task() -> int:
    """Периодический опрос: у CalDAV нет push, поэтому тянем окно на две недели раз в интервал."""
    session = SessionLocal()
    try:
        ids = list(
            session.scalars(
                select(CalendarConnection.id).where(CalendarConnection.status == ConnectionStatus.ACTIVE)
            )
        )
    finally:
        session.close()
    today = datetime.now(DomainConstants.DISPLAY_TZ).date()
    end = today + timedelta(days=DomainConstants.MAX_RANGE_DAYS - 1)
    for connection_id in ids:
        sync_connection_task.delay(str(connection_id), today.isoformat(), end.isoformat())
    return len(ids)


@worker_ready.connect
def _sync_on_worker_start(**_kwargs) -> None:
    """beat после рестарта ждёт полный интервал; синкаем сразу, чтобы данные не устаревали после выкладки."""
    sync_all_connections_task.delay()


def backoff_seconds(retries: int) -> int:
    """Экспоненциальная задержка между повторами: 30 с, 60 с, 120 с, ... не больше 15 минут."""
    return min(Constants.BACKOFF_BASE_SECONDS * (2**retries), Constants.BACKOFF_MAX_SECONDS)


def _is_transient(error: Exception) -> bool:
    if isinstance(error, HTTPStatusError):
        code = error.response.status_code
        return code == 429 or code >= 500
    if isinstance(error, httpx.TransportError):
        return True
    return False


class Constants:
    MAX_RETRIES = 4
    BACKOFF_BASE_SECONDS = 30
    BACKOFF_MAX_SECONDS = 900
