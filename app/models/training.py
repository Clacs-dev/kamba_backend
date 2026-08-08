"""
Modelos do plano de formação (secção 5).

- TrainingPlan: o plano de um período/ciclo, que a Administração aprova.
- TrainingAction: cada ação de formação dentro do plano, com a sua origem
  (sistema ou área), o colaborador visado e o estado.

Isolamento por company_id.
"""
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import TrainingSource, TrainingPlanStatus, TrainingActionStatus


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TrainingPlan(Base):
    __tablename__ = "training_plans"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)  # ex.: "Plano 2025"
    status: Mapped[TrainingPlanStatus] = mapped_column(
        Enum(TrainingPlanStatus), default=TrainingPlanStatus.RASCUNHO, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class TrainingAction(Base):
    __tablename__ = "training_actions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("training_plans.id", ondelete="CASCADE"), index=True, nullable=False
    )
    collaborator_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)      # ação formativa proposta
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[TrainingSource] = mapped_column(
        Enum(TrainingSource), default=TrainingSource.AREA, nullable=False
    )
    status: Mapped[TrainingActionStatus] = mapped_column(
        Enum(TrainingActionStatus), default=TrainingActionStatus.PROPOSTA, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
