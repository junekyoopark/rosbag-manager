import uuid
from datetime import datetime
from pydantic import BaseModel

from app.schemas.job import JobRead
from app.schemas.topic import TopicRead


class BagCreate(BaseModel):
    name: str | None = None
    description: str | None = None
    tags: list[str] = []


class BagListItem(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    status: str
    bag_format: str
    file_size_bytes: int
    rrd_size_bytes: int | None = None
    duration_sec: float | None = None
    message_count: int | None = None
    thumbnail_path: str | None = None
    tags: list[str] = []
    created_at: datetime
    topic_count: int = 0

    model_config = {"from_attributes": True}


class BagRead(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None = None
    status: str
    bag_format: str
    original_filename: str
    upload_path: str
    rrd_path: str | None = None
    rrd_url: str | None = None
    thumbnail_path: str | None = None
    file_size_bytes: int
    rrd_size_bytes: int | None = None
    duration_sec: float | None = None
    start_time_ns: int | None = None
    end_time_ns: int | None = None
    message_count: int | None = None
    tags: list[str] = []
    created_at: datetime
    updated_at: datetime
    job: JobRead | None = None
    topics: list[TopicRead] = []

    model_config = {"from_attributes": True}


class BagList(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[BagListItem]


class BagUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    published: bool | None = None
    team: list[str] | None = None


class BagUploadResponse(BaseModel):
    id: str
    name: str
    status: str
    job_id: str
    created_at: datetime
