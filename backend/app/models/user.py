import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(256), unique=True, nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(256), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="viewer")  # "admin" | "user" | "viewer"
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    can_upload_to_nas: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_import_from_nas: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    can_delete_own: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    team: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
