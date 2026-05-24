import uuid
from pydantic import BaseModel


class TopicRead(BaseModel):
    id: uuid.UUID
    bag_id: uuid.UUID
    name: str
    msg_type: str
    message_count: int | None = None
    frequency_hz: float | None = None
    serialization_format: str | None = None

    model_config = {"from_attributes": True}
