import uuid

from sqlalchemy import String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Setting(Base):
    """Backs the Settings page groups: system, detection, alerts, camera
    (Frontend Analysis Report §3.7)."""

    __tablename__ = "settings"
    __table_args__ = (
        UniqueConstraint("group_name", "key", name="uq_settings_group_key"),
        {"schema": "camera"},
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    group_name: Mapped[str] = mapped_column(String, nullable=False)
    key: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[dict] = mapped_column(JSONB, nullable=False)
