"""
Documentos anexados ao colaborador (contrato secção 2): BI, contrato assinado,
certificados de habilitações, etc. Ficheiros reais carregados (via Cloudinary).
Distingue-se do módulo /documents (que é texto integral de normas/políticas).
Isolamento por company_id.
"""
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class CollaboratorDocument(Base):
    __tablename__ = "collaborator_documents"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    collaborator_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    doc_type: Mapped[str] = mapped_column(String(50), nullable=False)  # bi|contrato_assinado|certificado_habilitacoes|outro
    file_url: Mapped[str | None] = mapped_column(String(500), nullable=True)  # URL do Cloudinary
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
