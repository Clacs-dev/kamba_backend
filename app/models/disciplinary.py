"""
Modelo do processo disciplinar (secção 4).
"""
from datetime import datetime, date, timezone

from sqlalchemy import String, Text, DateTime, Date, ForeignKey, Enum, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import DisciplinaryPhase, DisciplinaryOutcome


def _now() -> datetime:
    return datetime.now(timezone.utc)


class DisciplinaryProcess(Base):
    __tablename__ = "disciplinary_processes"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )

    accused_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    instructor_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    reference: Mapped[str] = mapped_column(String(100), nullable=False)
    phase: Mapped[DisciplinaryPhase] = mapped_column(
        Enum(DisciplinaryPhase), default=DisciplinaryPhase.INSTAURACAO, nullable=False
    )

    imputed_facts: Mapped[str] = mapped_column(Text, nullable=False)
    disciplinary_record: Mapped[str | None] = mapped_column(Text, nullable=True)

    charge_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    preventive_suspension: Mapped[bool] = mapped_column(Boolean, default=False)
    charge_ack_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    defense_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    defense_deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    defense_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    decision_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[DisciplinaryOutcome] = mapped_column(
        Enum(DisciplinaryOutcome), default=DisciplinaryOutcome.PENDENTE, nullable=False
    )

    decision_ack_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )