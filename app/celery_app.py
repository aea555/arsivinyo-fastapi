import os
from celery import Celery

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "media_downloader",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.tasks"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=600,  # 10 minutes max (hard limit)
    task_soft_time_limit=540,  # 9 minutes (soft limit, allows cleanup)
    worker_prefetch_multiplier=1,  # Only fetch 1 task at a time per worker
)

if __name__ == "__main__":
    celery_app.start()
