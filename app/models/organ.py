"""
Modelo dos Órgãos Sociais da empresa.

Cada órgão (Conselho de Administração, Comissão Executiva, Conselho Fiscal e
Mesa da Assembleia) tem colaboradores como membros, com um cargo dentro do
órgão (ex.: Presidente, Vice-presidente, Vogal). Um colaborador pode pertencer
a vários órgãos. Isolamento por company_id.
"""
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, ForeignKey, Enum, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import CompanyOrgan


def _now() -> datetime:
    return datetime.now(timezone.utc)


class OrganMember(Base):
    __tablename__ = "organ_members"
    __table_args__ = (
        UniqueConstraint("company_id", "organ", "user_id", name="uq_organs_company_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    organ: Mapped[CompanyOrgan] = mapped_column(
        Enum(CompanyOrgan), index=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    organ_role: Mapped[str | None] = mapped_column(String(100), nullable=True)
    appointed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    def __repr__(self) -> str:
        return f"<OrganMember organ={self.organ.value} user_id={self.user_id}>"