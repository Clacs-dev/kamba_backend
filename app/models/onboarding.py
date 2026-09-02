"""
Lista de verificação de acolhimento (secção 2.2).

Checklist do primeiro dia de cada colaborador — entrega de equipamento, acessos,
apresentações, formação inicial, etc. O Capital Humano marca os itens à medida
que são concluídos. Isolamento por company_id.
"""
from datetime import datetime, timezone

from sqlalchemy import String, Boolean, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class OnboardingItem(Base):
    __tablename__ = "onboarding_items"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    collaborator_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    done: Mapped[bool] = mapped_column(Boolean, default=False)
    applicable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # aplicável ao colaborador? (S/N)
    delivered: Mapped[bool | None] = mapped_column(Boolean, nullable=True)   # já foi entregue? (S/N)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
