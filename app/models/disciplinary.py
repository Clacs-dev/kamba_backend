"""
Modelo do processo disciplinar (secção 4).

Percorre seis fases obrigatórias. Cada campo corresponde a um ato processual
que só pode ser preenchido na fase certa. A plataforma não permite averbar
medida sem o processo ter percorrido todas as fases — é esta rigidez que
protege o trabalhador (direito de defesa) e a empresa (perante impugnação).

Isolamento por company_id.
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

    # Arguido (o trabalhador visado) e instrutor (quem conduz o processo).
    accused_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    instructor_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )

    reference: Mapped[str] = mapped_column(String(100), nullable=False)  # referência do processo
    phase: Mapped[DisciplinaryPhase] = mapped_column(
        Enum(DisciplinaryPhase), default=DisciplinaryPhase.INSTAURACAO, nullable=False
    )

    # Fase 1 — Instauração
    imputed_facts: Mapped[str] = mapped_column(Text, nullable=False)         # factos imputados
    disciplinary_record: Mapped[str | None] = mapped_column(Text, nullable=True)  # antecedentes

    # Fase 2 — Nota de culpa
    charge_note: Mapped[str | None] = mapped_column(Text, nullable=True)     # nota de culpa (factos + qualificação)
    preventive_suspension: Mapped[bool] = mapped_column(Boolean, default=False)
    charge_ack_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # assinatura de conhecimento

    # Fase 3 — Defesa
    defense_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    defense_deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    defense_submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Fase 4 — Decisão
    decision_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[DisciplinaryOutcome] = mapped_column(
        Enum(DisciplinaryOutcome), default=DisciplinaryOutcome.PENDENTE, nullable=False
    )

    # Fase 5 — Tomada de conhecimento da decisão
    decision_ack_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )


class DisciplinaryCommitteeMember(Base):
    """
    Membro da comissão disciplinar de um processo (alteração 11).

    Exactamente 3 membros por processo, todos com role=DIRECTOR — validado
    na rota (`disciplinary.py`), não aqui. Primeira associação N:M do
    projecto; segue o mesmo estilo dos restantes modelos (colunas FK
    escalares, sem `relationship()` ORM — a resolução para User é feita nas
    rotas, tal como já acontece com accused_id/instructor_id acima).
    """
    __tablename__ = "disciplinary_committee_members"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    process_id: Mapped[int] = mapped_column(
        ForeignKey("disciplinary_processes.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
