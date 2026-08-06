"""
Modelo EmployeeProfile — a ficha detalhada do colaborador (secção 2.1 do manual).
"""
from datetime import datetime, date, timezone

from sqlalchemy import String, DateTime, Date, ForeignKey, Enum, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import ContractType


def _now() -> datetime:
    return datetime.now(timezone.utc)


class EmployeeProfile(Base):
    __tablename__ = "employee_profiles"
    __table_args__ = (
        UniqueConstraint("company_id", "employee_number", name="uq_profile_company_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )

    employee_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    admission_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    contract_type: Mapped[ContractType | None] = mapped_column(Enum(ContractType), nullable=True)
    job_category: Mapped[str | None] = mapped_column(String(150), nullable=True)
    department: Mapped[str | None] = mapped_column(String(150), nullable=True)
    workplace: Mapped[str | None] = mapped_column(String(150), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    user: Mapped["User"] = relationship(back_populates="profile")