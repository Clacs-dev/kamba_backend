"""
Modelo do relatório de cultura — dados editados pelo Capital Humano.
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Text, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class CultureReport(Base):
    __tablename__ = "culture_reports"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False, unique=True
    )

    enps: Mapped[str | None] = mapped_column(String(50), nullable=True)
    participation: Mapped[str | None] = mapped_column(String(50), nullable=True)
    pulses_note: Mapped[str | None] = mapped_column(String(150), nullable=True)

    dimensions_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendations_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)