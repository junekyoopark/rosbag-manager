import uuid
from sqlalchemy import String, BigInteger, Float, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class Topic(Base):
    __tablename__ = "topics"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    bag_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bags.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    msg_type: Mapped[str] = mapped_column(String(256), nullable=False)
    message_count: Mapped[int | None] = mapped_column(BigInteger)
    frequency_hz: Mapped[float | None] = mapped_column(Float)
    serialization_format: Mapped[str | None] = mapped_column(String(32))

    bag: Mapped["Bag"] = relationship("Bag", back_populates="topics")
