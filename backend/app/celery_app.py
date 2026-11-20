from celery import Celery
from celery.signals import worker_init

from app.config import settings

celery_app = Celery("slot", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Moscow",
    enable_utc=True,
)

@worker_init.connect
def _require_secret(**_kwargs) -> None:
    settings.require_secret()


celery_app.autodiscover_tasks(["app.sync"])

celery_app.conf.beat_schedule = {
    "sync-all-connections": {
        "task": "sync_all_connections",
        "schedule": float(settings.sync_interval_seconds),
    }
}
