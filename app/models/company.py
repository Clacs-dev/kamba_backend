"""
Modelo Company — a empresa cliente.

É a unidade de isolamento multi-tenant (Opção A: tenant por coluna).
Cada colaborador, documento, avaliação e processo pertence a uma Company
através da coluna company_id, e todas as consultas filtram por ela.
"""
from datetime import datetime, timezone

from sqlalchemy import String, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    # NIF — Número de Identificação Fiscal (ver abreviaturas do manual).
    nif: Mapped[str | None] = mapped_column(String(50), unique=True, nullable=True)

    # Plano de subscrição (Essencial, Empresarial, Corporativo, Institucional).
    # Mantido como texto simples por agora; pode virar Enum quando afinarmos
    # as regras de cada plano (secção 10 do manual).
    plan: Mapped[str] = mapped_column(String(50), default="essencial")

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    # Relação: uma empresa tem muitos utilizadores.
    users: Mapped[list["User"]] = relationship(
        back_populates="company",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Company id={self.id} name={self.name!r}>"
