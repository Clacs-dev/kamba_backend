"""
Modelos da cultura organizacional (secção 6) — inquéritos-pulso anónimos.

ANONIMATO POR DESENHO — o ponto central deste módulo:
- SurveyResponse guarda as respostas SEM qualquer ligação ao utilizador.
- SurveyParticipation guarda apenas QUE um utilizador participou, sem o conteúdo.
Estas duas tabelas nunca se cruzam, por isso é impossível ligar uma resposta
a uma pessoa. A participação serve só para impedir dupla resposta.

Além disso, os resultados só são revelados com pelo menos 5 respostas (regra
do manual), o que se aplica na camada de leitura.
"""
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime, ForeignKey, Enum, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import SurveyStatus


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Survey(Base):
    """Um inquérito-pulso trimestral."""
    __tablename__ = "surveys"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    # Dimensões medidas, guardadas como JSON (lista de chaves). Ex.:
    # ["confianca_lideranca","clareza_estrategica","reconhecimento",...]
    dimensions: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[SurveyStatus] = mapped_column(
        Enum(SurveyStatus), default=SurveyStatus.ABERTO, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SurveyResponse(Base):
    """
    Uma resposta anónima. NÃO tem user_id — de propósito.
    Guarda só o inquérito, a empresa e as respostas (JSON: dimensão -> 1..5).
    """
    __tablename__ = "survey_responses"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    survey_id: Mapped[int] = mapped_column(
        ForeignKey("surveys.id", ondelete="CASCADE"), index=True, nullable=False
    )
    answers: Mapped[str] = mapped_column(Text, nullable=False)  # JSON dimensão->valor
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SurveyParticipation(Base):
    """
    Regista APENAS que um utilizador participou (para impedir dupla resposta).
    NÃO contém o conteúdo da resposta. Nunca se cruza com SurveyResponse.
    """
    __tablename__ = "survey_participations"
    __table_args__ = (
        UniqueConstraint("survey_id", "user_id", name="uq_participation_survey_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    survey_id: Mapped[int] = mapped_column(
        ForeignKey("surveys.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    participated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
