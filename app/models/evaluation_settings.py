"""
Parametrização do ciclo de avaliação por empresa (secção 8 do manual).

Cada empresa pode ajustar as ponderações por categoria, o prazo de recurso
(em dias úteis) e o calendário do ciclo. Os valores por defeito seguem o
manual (técnico 50/35/15, dirigente 60/25/15, recurso 8 dias úteis).
Isolamento por company_id (uma linha por empresa).
"""
from datetime import datetime, timezone

from sqlalchemy import Integer, Float, String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class EvaluationSettings(Base):
    __tablename__ = "evaluation_settings"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )

    # Ponderações do técnico (têm de somar 1.0).
    tec_objectives: Mapped[float] = mapped_column(Float, default=0.50)
    tec_competencies: Mapped[float] = mapped_column(Float, default=0.35)
    tec_values: Mapped[float] = mapped_column(Float, default=0.15)

    # Ponderações do dirigente (têm de somar 1.0).
    dir_objectives: Mapped[float] = mapped_column(Float, default=0.60)
    dir_competencies: Mapped[float] = mapped_column(Float, default=0.25)
    dir_values: Mapped[float] = mapped_column(Float, default=0.15)

    # Prazo de recurso à comissão, em dias úteis (secção 3.1 / 8).
    appeal_deadline_days: Mapped[int] = mapped_column(Integer, default=8)

    # Calendário do ciclo (texto livre, ex.: "Janeiro a Dezembro").
    cycle_calendar: Mapped[str | None] = mapped_column(String(200), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
