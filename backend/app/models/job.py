import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, SmallInteger, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class ConversionJob(Base):
    __tablename__ = "conversion_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    bag_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bags.id", ondelete="CASCADE"), nullable=False
    )
    celery_task_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    progress_pct: Mapped[int] = mapped_column(SmallInteger, default=0)
    current_step: Mapped[str | None] = mapped_column(String(128))
    error_message: Mapped[str | None] = mapped_column(Text)
    worker_hostname: Mapped[str | None] = mapped_column(String(255))
    queued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    bag: Mapped["Bag"] = relationship("Bag", back_populates="job")
