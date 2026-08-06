"""
Modelos da cultura organizacional (secção 6) — inquéritos-pulso anónimos.

ANONIMATO POR DESENHO:
- SurveyResponse guarda as respostas SEM ligação ao utilizador.
- SurveyParticipation guarda apenas QUE um utilizador participou, sem conteúdo.
As duas tabelas nunca se cruzam.
"""
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime, ForeignKey, Enum, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import SurveyStatus


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Survey(Base):
    __tablename__ = "surveys"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    dimensions: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[SurveyStatus] = mapped_column(
        Enum(SurveyStatus), default=SurveyStatus.ABERTO, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SurveyResponse(Base):
    __tablename__ = "survey_responses"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    survey_id: Mapped[int] = mapped_column(
        ForeignKey("surveys.id", ondelete="CASCADE"), index=True, nullable=False
    )
    answers: Mapped[str] = mapped_column(Text, nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class SurveyParticipation(Base):
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