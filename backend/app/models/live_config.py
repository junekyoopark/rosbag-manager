from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class LiveConfig(Base):
    __tablename__ = "live_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    scan_subnet: Mapped[str] = mapped_column(String(64), nullable=False, default="")
