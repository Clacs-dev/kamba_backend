"""
Pedido de correção da ficha (secção 2.1).

O colaborador consulta a sua ficha e pode requerer correções: submete um pedido
com a descrição do que considera incorreto. O Capital Humano vê os pedidos e
resolve-os (depois de corrigir a ficha). Isolamento por company_id.
"""
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class FichaCorrectionRequest(Base):
    __tablename__ = "ficha_correction_requests"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    collaborator_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    message: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="pendente")  # pendente | resolvido
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
