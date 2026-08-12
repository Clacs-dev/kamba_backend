"""
Modelo EmployeeProfile — a ficha detalhada do colaborador (secção 2.1 do manual).

Está separada da tabela `users` de propósito: `users` guarda a conta de acesso
(email, password, perfil), enquanto `employee_profiles` guarda os dados
profissionais (número, admissão, vínculo, categoria, direção, local). Relação
um-para-um. Isto mantém a autenticação limpa e a ficha pode crescer sem tocar
no login.

Pertence sempre a uma empresa (company_id) — parte do isolamento multi-tenant.
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
        # Número de colaborador único DENTRO de cada empresa.
        UniqueConstraint("company_id", "employee_number", name="uq_profile_company_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Ligação ao utilizador (um-para-um) e à empresa (tenant).
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # --- Campos da ficha (secção 2.1) ---
    employee_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    admission_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    contract_type: Mapped[ContractType | None] = mapped_column(
        Enum(ContractType), nullable=True
    )
    job_category: Mapped[str | None] = mapped_column(String(150), nullable=True)  # categoria profissional
    job_title: Mapped[str | None] = mapped_column(String(150), nullable=True)     # cargo específico (ex.: Chefe de Vendas)
    department: Mapped[str | None] = mapped_column(String(150), nullable=True)    # direção / área
    workplace: Mapped[str | None] = mapped_column(String(150), nullable=True)     # local de trabalho
    work_schedule: Mapped[str | None] = mapped_column(String(200), nullable=True) # horário (ex.: 2.ª a 6.ª · 08h00-16h30)
    situation_tags: Mapped[str | None] = mapped_column(String(300), nullable=True) # etiquetas livres, separadas por vírgula

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    # Relação inversa para o utilizador.
    user: Mapped["User"] = relationship(back_populates="profile")

    def __repr__(self) -> str:
        return f"<EmployeeProfile user_id={self.user_id} number={self.employee_number!r}>"
