from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta

from httpx import HTTPStatusError

from app.adapters import apple, google, yandex
from app.adapters.caldav_client import CalDavAuthError
from app.celery_app import celery_app
from app.db import SessionLocal
from app.domain import Constants as DomainConstants
from app.models import ConnectionStatus, Provider
from app.services.connections import get_connection, load_secret, refresh_if_needed, replace_busy_window

logger = logging.getLogger(__name__)


@celery_app.task(name="sync_connection")
def sync_connection_task(connection_id: str, date_from: str, date_to: str) -> None:
    session = SessionLocal()
    try:
        connection = get_connection(session, uuid.UUID(connection_id))
        connection.status = ConnectionStatus.SYNCING
        connection.last_error = None
        session.commit()
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
    except (CalDavAuthError, HTTPStatusError) as error:
        session.rollback()
        _mark_failed(session, connection_id, str(error), auth_failed=True)
    except Exception:
        logger.exception("sync failed for %s", connection_id)
        session.rollback()
        _mark_failed(session, connection_id, "Не удалось обновить календарь", auth_failed=False)
        raise
    finally:
        session.close()


def _fetch(provider: str, secret: dict, external_id: str, window_start: datetime, window_end: datetime):
    if provider == Provider.GOOGLE:
        return google.fetch_busy(secret, external_id, window_start, window_end)
    if provider == Provider.YANDEX:
        return yandex.fetch_busy(secret, external_id, window_start, window_end)
    return apple.fetch_busy(secret, external_id, window_start, window_end)


def _mark_failed(session, connection_id: str, message: str, auth_failed: bool) -> None:
    try:
        connection = get_connection(session, uuid.UUID(connection_id))
        connection.status = ConnectionStatus.AUTH_FAILED if auth_failed else ConnectionStatus.ACTIVE
        connection.last_error = message[:2000]
        session.commit()
    except Exception:
        session.rollback()
