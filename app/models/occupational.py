"""
Modelo de Saúde Ocupacional (secção 2.7).

PRIVACIDADE POR DESENHO — o ponto central deste módulo:
O modelo regista APENAS a aptidão laboral e as datas. NÃO existe qualquer
campo para diagnóstico, sintomas ou dados clínicos — esses permanecem na
esfera do médico do trabalho, fora da plataforma. Esta ausência é
intencional e estrutural.

Isolamento por company_id.
"""
from datetime import datetime, date, timezone

from sqlalchemy import String, DateTime, Date, ForeignKey, Enum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import FitnessResult


def _now() -> datetime:
    return datetime.now(timezone.utc)


class OccupationalExam(Base):
    __tablename__ = "occupational_exams"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    collaborator_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # Só aptidão e datas — nunca diagnósticos.
    fitness: Mapped[FitnessResult] = mapped_column(Enum(FitnessResult), nullable=False)
    exam_date: Mapped[date] = mapped_column(Date, nullable=False)          # data do exame
    next_exam_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # próximo exame previsto

    # Uma nota opcional NÃO clínica (ex.: "restrição a trabalho noturno").
    restriction_note: Mapped[str | None] = mapped_column(String(300), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
