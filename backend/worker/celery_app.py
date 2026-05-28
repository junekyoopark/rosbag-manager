from celery import Celery
from app.config import settings

celery_app = Celery(
    "rosbag_worker",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["worker.tasks.convert", "worker.tasks.introspect",
             "worker.tasks.nas_upload", "worker.tasks.nas_import",
             "worker.tasks.sftp_import"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
)
