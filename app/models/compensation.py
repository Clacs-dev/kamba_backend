"""
Modelos de Remuneração e Assiduidade (secção 2.8).

- SalaryRecord: um registo de progressão salarial (com o ano, o salário e o
  enquadramento na tabela). O histórico de registos mostra a progressão.
- AttendanceRecord: indicadores de assiduidade por período (presenças, faltas
  justificadas e injustificadas, férias gozadas).

Visibilidade (aplicada nas rotas): próprio, Capital Humano e Administração.
Isolamento por company_id.
"""
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, ForeignKey, Integer, Float
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SalaryRecord(Base):
    """Um registo de progressão salarial (por ano)."""
    __tablename__ = "salary_records"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    collaborator_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    year: Mapped[int] = mapped_column(Integer, nullable=False)
    gross_salary: Mapped[float] = mapped_column(Float, nullable=False)     # salário bruto
    salary_grade: Mapped[str | None] = mapped_column(String(100), nullable=True)  # enquadramento na tabela

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class AttendanceRecord(Base):
    """Indicadores de assiduidade de um período (ex.: um ano)."""
    __tablename__ = "attendance_records"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    collaborator_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    period: Mapped[str] = mapped_column(String(50), nullable=False)  # ex.: "2025" ou "2025-Q1"
    present_days: Mapped[int] = mapped_column(Integer, default=0)
    justified_absences: Mapped[int] = mapped_column(Integer, default=0)
    unjustified_absences: Mapped[int] = mapped_column(Integer, default=0)
    vacation_days_taken: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
