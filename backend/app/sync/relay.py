from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from time import sleep

from kombu.exceptions import OperationalError as BrokerError
from redis.exceptions import RedisError
from sqlalchemy import and_, or_, select
from sqlalchemy.exc import InterfaceError, OperationalError

from app.config import settings
from app.db import SessionLocal
from app.models import SyncJob, SyncStatus
from app.sync.tasks import sync_connection_task

logger = logging.getLogger(__name__)


def publish_next() -> bool:
    now = datetime.now(timezone.utc)
    stale = now - timedelta(seconds=settings.sync_visibility_timeout + 60)
    with SessionLocal.begin() as session:
        job = session.scalar(
            select(SyncJob)
            .where(
                SyncJob.status.in_((SyncStatus.QUEUED, SyncStatus.RUNNING)),
                SyncJob.available_at <= now,
                or_(
                    SyncJob.published_at.is_(None),
                    and_(SyncJob.published_at < stale, SyncJob.activity_at < stale),
                ),
            )
            .order_by(SyncJob.available_at, SyncJob.id)
            .limit(1)
            .with_for_update(skip_locked=True)
        )
        if job is None:
            return False
        job_id, retries = str(job.id), job.retries
        recovering = job.published_at is not None
        sync_connection_task.apply_async(args=(job_id, retries), task_id=job_id, retry=False)
        job.published_at = datetime.now(timezone.utc)
    logger.info("%s job_id=%s retries=%s", "republished" if recovering else "published", job_id, retries)
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    while True:
        try:
            if not publish_next():
                sleep(1)
        except (OperationalError, InterfaceError, BrokerError, RedisError) as error:
            logger.warning("publication_delayed error=%s", type(error).__name__)
            sleep(2)


if __name__ == "__main__":
    main()
