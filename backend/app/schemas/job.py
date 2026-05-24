import uuid
from datetime import datetime
from pydantic import BaseModel


class JobRead(BaseModel):
    id: uuid.UUID
    bag_id: uuid.UUID
    celery_task_id: str | None = None
    status: str
    progress_pct: int = 0
    current_step: str | None = None
    error_message: str | None = None
    worker_hostname: str | None = None
    queued_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None

    model_config = {"from_attributes": True}
