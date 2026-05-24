import uuid
from datetime import datetime, timezone
from sqlalchemy import String, Text, BigInteger, Float, DateTime, ARRAY, ForeignKey, Boolean
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Bag(Base):
    __tablename__ = "bags"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    bag_format: Mapped[str] = mapped_column(String(16), nullable=False)
    upload_path: Mapped[str] = mapped_column(Text, nullable=False)
    rrd_path: Mapped[str | None] = mapped_column(Text)
    rrd_url: Mapped[str | None] = mapped_column(Text)
    thumbnail_path: Mapped[str | None] = mapped_column(Text)
    file_size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rrd_size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    duration_sec: Mapped[float | None] = mapped_column(Float)
    start_time_ns: Mapped[int | None] = mapped_column(BigInteger)
    end_time_ns: Mapped[int | None] = mapped_column(BigInteger)
    message_count: Mapped[int | None] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    tags: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    published: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    uploader: Mapped["User | None"] = relationship("User", foreign_keys=[uploaded_by_id])
    topics: Mapped[list["Topic"]] = relationship(
        "Topic", back_populates="bag", cascade="all, delete-orphan"
    )
    job: Mapped["ConversionJob | None"] = relationship(
        "ConversionJob",
        back_populates="bag",
        cascade="all, delete-orphan",
        uselist=False,
    )
