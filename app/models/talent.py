"""
Modelos do Comité de Talento — matriz 9-Box e plano de sucessão.

O 9-Box cruza Desempenho (vem das avaliações validadas) com Potencial (juízo
do comité) e alimenta o plano de sucessão: por cargo-chave, quem é o sucessor
e com que prontidão. É a secção "Talento & Sucessão" dos relatórios.

Isolamento por company_id.
"""
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime, ForeignKey, Enum, Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import PotentialLevel, ReadinessLevel


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TalentMatrix(Base):
    """Atribuição de potencial (eixo do comité) a um colaborador num ciclo."""
    __tablename__ = "talent_matrix"
    __table_args__ = (
        # Um registo de potencial por colaborador em cada ciclo.
        UniqueConstraint("cycle_id", "collaborator_id", name="uq_talent_cycle_collab"),
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

    potential: Mapped[PotentialLevel] = mapped_column(
        Enum(PotentialLevel), nullable=False
    )
    # Cargo atual no 9-Box (opcional, ajuda o comité a ler a matriz).
    position: Mapped[str | None] = mapped_column(String(150), nullable=True)
    # Risco de saída percecionado (sucessão crítica).
    risk_of_exit: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class SuccessionPlan(Base):
    """Plano de sucessão para um cargo-chave da empresa."""
    __tablename__ = "succession_plans"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    role_title: Mapped[str] = mapped_column(String(150), nullable=False)  # cargo-chave
    incumbent_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=True
    )
    successor_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    readiness: Mapped[ReadinessLevel] = mapped_column(
        Enum(ReadinessLevel), default=ReadinessLevel.EM_12_MESES, nullable=False
    )
    risk_of_exit: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )