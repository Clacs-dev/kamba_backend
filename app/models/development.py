"""
Modelos do Plano Individual de Desenvolvimento (PID) — secção 5.

O PID regista ações de desenvolvimento por colaborador; as suas ações
pendentes alimentam as necessidades de formação identificadas pelo sistema.

Isolamento por company_id.
"""
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime, Integer, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import DevelopmentPlanStatus, DevelopmentActionStatus


def _now() -> datetime:
    return datetime.now(timezone.utc)


class DevelopmentPlan(Base):
    __tablename__ = "development_plans"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    collaborator_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[DevelopmentPlanStatus] = mapped_column(
        Enum(DevelopmentPlanStatus), default=DevelopmentPlanStatus.ABERTO, nullable=False
    )
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class DevelopmentAction(Base):
    __tablename__ = "development_actions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    plan_id: Mapped[int] = mapped_column(
        ForeignKey("development_plans.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[DevelopmentActionStatus] = mapped_column(
        Enum(DevelopmentActionStatus), default=DevelopmentActionStatus.PENDENTE, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
