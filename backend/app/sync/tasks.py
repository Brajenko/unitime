from __future__ import annotations

import logging
import random
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from time import sleep

import httpx
from celery.exceptions import Reject
from celery.signals import worker_ready
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import InterfaceError, OperationalError

from app.adapters import BusyOccurrence, apple, google, link, yandex
from app.adapters.caldav_client import CalDavAuthError
from app.celery_app import celery_app
from app.config import settings
from app.db import SessionLocal
from app.domain import Constants as DomainConstants
from app.models import CalendarConnection, ConnectionStatus, Provider, SyncJob, SyncStatus
from app.services import cache
from app.services.connections import get_connection, load_secret, refresh_if_needed, replace_busy_window, save_secret

logger = logging.getLogger(__name__)


class Constants:
    MAX_RETRIES = 4
    BACKOFF_BASE_SECONDS = 30
    BACKOFF_MAX_SECONDS = 900
    DATABASE_REQUEUE_DELAY_SECONDS = 2
    SOFT_TIME_LIMIT_SECONDS = 50
    TIME_LIMIT_SECONDS = 60
    SPREAD_SHARE = 0.8
    SPREAD_JITTER = 0.1


@dataclass(frozen=True)
class Attempt:
    job_id: uuid.UUID
    connection_id: uuid.UUID
    start: date
    end: date
    number: int
    retries: int


@dataclass
class CalendarSnapshot:
    encrypted_secret: bytes
    refreshed_secret: dict | None
    window_start: datetime
    window_end: datetime
    occurrences: dict[uuid.UUID, list[BusyOccurrence]]


@celery_app.task(
    name="sync_calendar_job", bind=True, acks_late=True, reject_on_worker_lost=True, ignore_result=True,
    soft_time_limit=Constants.SOFT_TIME_LIMIT_SECONDS,
    time_limit=Constants.TIME_LIMIT_SECONDS,
)
def sync_connection_task(self, job_id: str, retries: int) -> None:
    worker = self.request.hostname
    redelivered = str(bool(self.request.delivery_info.get("redelivered"))).lower()
    try:
        attempt = _start_attempt(uuid.UUID(job_id), retries, worker, redelivered)
        if attempt is None:
            return
        try:
            snapshot = _collect_calendar(attempt)
            applied = _save_result(attempt, snapshot)
        except (OperationalError, InterfaceError):
            raise
        except Exception as error:
            _record_failure(attempt, error)
        else:
            outcome = "committed" if applied else "superseded"
            logger.info("%s job_id=%s attempt=%s worker=%s", outcome, job_id, attempt.number, worker)
    except (OperationalError, InterfaceError) as error:
        logger.warning(
            "requeue_database job_id=%s worker=%s error=%s", job_id, worker, type(error).__name__
        )
        sleep(Constants.DATABASE_REQUEUE_DELAY_SECONDS)
        raise Reject(error, requeue=True) from error


def _start_attempt(job_id: uuid.UUID, retries: int, worker: str, redelivered: str) -> Attempt | None:
    duplicate_user = None
    attempt = None
    with SessionLocal.begin() as session:
        job = session.get(SyncJob, job_id, with_for_update=True)
        if job is None:
            logger.info("missing job_id=%s worker=%s", job_id, worker)
            return None
        if job.status in (SyncStatus.SUCCEEDED, SyncStatus.FAILED):
            logger.info(
                "duplicate job_id=%s attempt=%s worker=%s redelivered=%s",
                job.id, job.attempts, worker, redelivered,
            )
            if job.status == SyncStatus.SUCCEEDED:
                duplicate_user = session.scalar(
                    select(CalendarConnection.user_id).where(CalendarConnection.id == job.connection_id)
                )
        elif job.retries != retries:
            logger.info("superseded job_id=%s worker=%s", job.id, worker)
            return None
        else:
            connection = session.get(CalendarConnection, job.connection_id, with_for_update=True)
            job.attempts += 1
            job.status = SyncStatus.RUNNING
            job.activity_at = datetime.now(timezone.utc)
            connection.status = ConnectionStatus.SYNCING
            connection.last_error = None
            attempt = Attempt(job.id, job.connection_id, job.date_from, job.date_to, job.attempts, retries)
            user_id = connection.user_id
    if duplicate_user is not None:
        cache.bump_user(duplicate_user)
    if attempt is None:
        return None
    cache.bump_user(user_id)
    logger.info(
        "running job_id=%s attempt=%s worker=%s redelivered=%s",
        job_id, attempt.number, worker, redelivered,
    )
    return attempt


def _collect_calendar(attempt: Attempt) -> CalendarSnapshot:
    with SessionLocal() as session:
        connection = get_connection(session, attempt.connection_id)
        provider = connection.provider
        encrypted_secret = connection.encrypted_secret
        old_secret = load_secret(connection)
        selected = [(item.id, item.external_id) for item in connection.collections if item.selected]
    secret = refresh_if_needed(provider, old_secret)
    window_start = datetime.combine(attempt.start, datetime.min.time(), tzinfo=DomainConstants.DISPLAY_TZ)
    window_end = datetime.combine(
        attempt.end + timedelta(days=1), datetime.min.time(), tzinfo=DomainConstants.DISPLAY_TZ
    )
    occurrences = {
        collection_id: _fetch(provider, secret, external_id, window_start, window_end)
        for collection_id, external_id in selected
    }
    return CalendarSnapshot(
        encrypted_secret, secret if secret is not old_secret else None, window_start, window_end, occurrences,
    )


def _owns_attempt(job: SyncJob | None, attempt: Attempt) -> bool:
    return job is not None and job.status == SyncStatus.RUNNING and job.attempts == attempt.number


def _save_result(attempt: Attempt, snapshot: CalendarSnapshot) -> bool:
    with SessionLocal.begin() as session:
        job = session.get(SyncJob, attempt.job_id, with_for_update=True)
        if not _owns_attempt(job, attempt):
            return False
        connection = session.get(CalendarConnection, attempt.connection_id, with_for_update=True)
        if snapshot.refreshed_secret is not None and connection.encrypted_secret == snapshot.encrypted_secret:
            save_secret(connection, snapshot.refreshed_secret)
        job.interval_count = sum(
            replace_busy_window(
                session, collection, snapshot.window_start, snapshot.window_end, snapshot.occurrences[collection.id]
            )
            for collection in connection.collections
            if collection.selected and collection.id in snapshot.occurrences
        )
        finished_at = datetime.now(timezone.utc)
        connection.status = ConnectionStatus.ACTIVE
        connection.last_error = None
        connection.last_synced_at = finished_at
        user_id = connection.user_id
        job.status = SyncStatus.SUCCEEDED
        job.finished_at = finished_at
        job.process_count += 1
    cache.bump_user(user_id)
    return True


def _record_failure(attempt: Attempt, error: Exception) -> None:
    auth_failed = isinstance(error, (link.LinkError, CalDavAuthError, httpx.HTTPStatusError)) and not _is_transient(error)
    if isinstance(error, link.LinkError):
        message = str(error)
    elif auth_failed:
        message = "Не удалось получить доступ к календарю"
    elif _is_transient(error):
        message = "Провайдер временно недоступен"
    else:
        logger.exception("calendar_error job_id=%s attempt=%s", attempt.job_id, attempt.number)
        message = "Не удалось обновить календарь"
    with SessionLocal.begin() as session:
        job = session.get(SyncJob, attempt.job_id, with_for_update=True)
        if not _owns_attempt(job, attempt):
            return
        connection = session.get(CalendarConnection, attempt.connection_id, with_for_update=True)
        connection.status = ConnectionStatus.AUTH_FAILED if auth_failed else ConnectionStatus.ACTIVE
        connection.last_error = message[:2000]
        job.error = connection.last_error
        user_id = connection.user_id
        now = datetime.now(timezone.utc)
        if not auth_failed and job.retries < Constants.MAX_RETRIES:
            job.available_at = now + timedelta(seconds=backoff_seconds(job.retries))
            job.retries += 1
            job.status = SyncStatus.QUEUED
            job.published_at = None
            job.activity_at = now
        else:
            job.status = SyncStatus.FAILED
            job.finished_at = now
        outcome = job.status
    cache.bump_user(user_id)
    logger.info("%s job_id=%s attempt=%s", outcome, attempt.job_id, attempt.number)


def _fetch(provider: str, secret: dict, external_id: str, window_start: datetime, window_end: datetime):
    if provider == Provider.GOOGLE:
        return google.fetch_busy(secret, external_id, window_start, window_end)
    if provider == Provider.YANDEX:
        return yandex.fetch_busy(secret, external_id, window_start, window_end)
    if provider == Provider.LINK:
        return link.fetch_busy(secret, external_id, window_start, window_end)
    return apple.fetch_busy(secret, external_id, window_start, window_end)


@celery_app.task(name="sync_connection", bind=True, acks_late=True, reject_on_worker_lost=True, ignore_result=True)
def import_queued_sync(self, connection_id: str, date_from: str, date_to: str) -> None:
    """Move deliveries published by a previous version to the durable queue."""
    try:
        with SessionLocal.begin() as session:
            connection = session.get(
                CalendarConnection, uuid.UUID(connection_id), with_for_update={"read": True, "key_share": True}
            )
            if connection is not None:
                session.execute(
                    insert(SyncJob).values(
                        id=uuid.UUID(self.request.id), connection_id=connection.id,
                        date_from=date.fromisoformat(date_from), date_to=date.fromisoformat(date_to),
                    ).on_conflict_do_nothing(index_elements=[SyncJob.id])
                )
    except (OperationalError, InterfaceError) as error:
        sleep(Constants.DATABASE_REQUEUE_DELAY_SECONDS)
        raise Reject(error, requeue=True) from error


@celery_app.task(name="sync_all_connections")
def sync_all_connections_task() -> int:
    """Периодический опрос активных подключений на две недели."""
    with SessionLocal.begin() as session:
        ids = list(
            session.scalars(
                select(CalendarConnection.id)
                .where(CalendarConnection.status == ConnectionStatus.ACTIVE)
                .with_for_update(read=True, key_share=True)
            )
        )
        now = datetime.now(timezone.utc)
        today = now.astimezone(DomainConstants.DISPLAY_TZ).date()
        end = today + timedelta(days=DomainConstants.MAX_RANGE_DAYS - 1)
        delays = spread_countdowns(len(ids), settings.sync_interval_seconds)
        session.add_all(
            SyncJob(
                connection_id=connection_id,
                date_from=today,
                date_to=end,
                available_at=now + timedelta(seconds=delay),
            )
            for connection_id, delay in zip(ids, delays)
        )
    return len(ids)


@worker_ready.connect
def _sync_on_worker_start(**_kwargs) -> None:
    if settings.sync_on_worker_start:
        sync_all_connections_task.delay()


def spread_countdowns(count: int, interval_seconds: int) -> list[float]:
    """Разносит постановку `count` задач по первым 80% интервала, чтобы пачка не забивала воркер.

    Шаг равномерный, к каждой задержке добавлен случайный сдвиг до ±10% шага (порядок не нарушается).
    """
    if count <= 0:
        return []
    step = interval_seconds * Constants.SPREAD_SHARE / count
    jitter = step * Constants.SPREAD_JITTER
    return [max(0.0, index * step + random.uniform(-jitter, jitter)) for index in range(count)]


def backoff_seconds(retries: int) -> int:
    """Экспоненциальная задержка между повторами, не больше 15 минут."""
    return min(Constants.BACKOFF_BASE_SECONDS * (2**retries), Constants.BACKOFF_MAX_SECONDS)


def _is_transient(error: Exception) -> bool:
    if isinstance(error, httpx.HTTPStatusError):
        code = error.response.status_code
        return code == 429 or code >= 500
    return isinstance(error, httpx.TransportError)
