import uuid

from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class Sector(Base):
    __tablename__ = "sectors"
    __table_args__ = {"schema": "camera"}

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String, unique=True, nullable=False)
