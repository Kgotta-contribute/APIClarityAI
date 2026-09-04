import os
from celery import Celery
from app.config.config import settings

REDIS_URL = os.getenv("REDIS_URL") or getattr(settings, "redis_url", "redis://localhost:6379/0")

celery_app = Celery(
    "clarity_tasks",
    broker=REDIS_URL,
    backend=REDIS_URL
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
)
