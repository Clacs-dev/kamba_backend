"""
Modelos do ciclo de avaliação de desempenho (secção 3).

- EvaluationCycle: um ciclo anual da empresa (ex.: "Avaliação 2025").
- Evaluation: a avaliação de um colaborador dentro de um ciclo, que percorre
  as seis fases. Guarda as respostas dos três blocos (objetivos, competências,
  valores) e a pontuação calculada.

As respostas são guardadas como JSON (texto) para flexibilidade — os objetivos
variam em número e peso por colaborador. Isolamento por company_id.
"""
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime, ForeignKey, Enum, Boolean, Float, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import EvaluationPhase, EvaluationCategory


def _now() -> datetime:
    return datetime.now(timezone.utc)


class EvaluationCycle(Base):
    """Um ciclo de avaliação da empresa (normalmente anual)."""
    __tablename__ = "evaluation_cycles"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)  # ex.: "Ciclo 2025"
    is_open: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Evaluation(Base):
    """A avaliação de um colaborador num ciclo. Percorre as seis fases."""
    __tablename__ = "evaluations"
    __table_args__ = (
        # Um colaborador tem no máximo uma avaliação por ciclo.
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

    # Respostas guardadas como JSON (texto).
    self_answers: Mapped[str | None] = mapped_column(Text, nullable=True)      # autoavaliação
    director_answers: Mapped[str | None] = mapped_column(Text, nullable=True)  # avaliação do director

    # Pontuação final (da avaliação do director) e classificação.
    final_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    classification: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # Recurso (fase 3->4).
    appeal_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    appeal_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    commission_decision: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
