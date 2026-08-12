"""
Pedidos de férias e ausências — alinhado ao contrato do frontend.

Máquina de estados (do contrato):
- Férias: pendente_dir -> aprovada (ou -> recusada, com rejection_reason).
- Falta com documento: entra direto como justificada.
- Maternidade: criada já como aprovada (registo administrativo do CH).
O campo 'averbado' marca que foi averbado no mapa anual (secção 1.7).
Isolamento por company_id.
"""
from datetime import datetime, timezone, date

from sqlalchemy import String, Text, Integer, Date, DateTime, Boolean, ForeignKey, Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import LeaveType, LeaveStatus


def _now() -> datetime:
    return datetime.now(timezone.utc)


class LeaveRequest(Base):
    __tablename__ = "leave_requests"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    collaborator_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    leave_type: Mapped[LeaveType] = mapped_column(SAEnum(LeaveType), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    days: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Documento comprovativo (nome para exibição + URL do Cloudinary).
    document_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    document_url: Mapped[str | None] = mapped_column(String(500), nullable=True)

    status: Mapped[LeaveStatus] = mapped_column(SAEnum(LeaveStatus), nullable=False)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    averbado: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
