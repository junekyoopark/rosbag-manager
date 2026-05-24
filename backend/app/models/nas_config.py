from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class NASConfig(Base):
    __tablename__ = "nas_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    dsm_url: Mapped[str | None] = mapped_column(String(512))
    username: Mapped[str | None] = mapped_column(String(128))
    encrypted_password: Mapped[str | None] = mapped_column(Text)
    upload_path: Mapped[str] = mapped_column(String(512), nullable=False, default="/rosbags")
    verify_ssl: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
