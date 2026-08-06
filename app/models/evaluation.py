"""
Modelos do ciclo de avaliação de desempenho (secção 3).
"""
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime, ForeignKey, Enum, Boolean, Float, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import EvaluationPhase, EvaluationCategory


def _now() -> datetime:
    return datetime.now(timezone.utc)


class EvaluationCycle(Base):
    __tablename__ = "evaluation_cycles"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Evaluation(Base):
    __tablename__ = "evaluations"
    __table_args__ = (
        UniqueConstraint("cycle_id", "collaborator_id", name="uq_eval_cycle_collab"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    cycle_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_cycles.id", ondelete="CASCADE"), index=True, nullable=False
    )
    collaborator_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    director_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    category: Mapped[EvaluationCategory] = mapped_column(
        Enum(EvaluationCategory), default=EvaluationCategory.TECNICO, nullable=False
    )
    phase: Mapped[EvaluationPhase] = mapped_column(
        Enum(EvaluationPhase), default=EvaluationPhase.AUTOAVALIACAO, nullable=False
    )

    self_answers: Mapped[str | None] = mapped_column(Text, nullable=True)
    director_answers: Mapped[str | None] = mapped_column(Text, nullable=True)

    final_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    classification: Mapped[str | None] = mapped_column(String(30), nullable=True)

    appeal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    commission_decision: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )