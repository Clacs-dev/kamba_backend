"""
Modelo de eventos manuais do percurso (secção 2.3).

Guarda apenas os marcos que NÃO vêm automaticamente de outros módulos —
louvores, nomeações, promoções. Os restantes eventos (admissão, avaliações,
disciplina, exames, formações) são agregados na hora, na rota do percurso,
a partir dos módulos respetivos.

Isolamento por company_id.
"""
from datetime import datetime, date, timezone

from sqlalchemy import String, Text, DateTime, Date, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import CareerEventType


def _now() -> datetime:
    return datetime.now(timezone.utc)


class CareerEvent(Base):
    __tablename__ = "career_events"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    collaborator_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    event_type: Mapped[CareerEventType] = mapped_column(
        Enum(CareerEventType), default=CareerEventType.OUTRO, nullable=False
    )
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
