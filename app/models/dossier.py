"""
Modelos do dossier: Documentos, registos de leitura e assinaturas (secções 2.2 e 2.4).

- Document: um documento com texto integral, pertencente a uma empresa.
- DocumentRead: registo de cada abertura/leitura por um colaborador (a prova
  jurídica de que a empresa comunicou as normas).
- Signature: as três assinaturas digitais de adesão, com carimbo temporal.

Tudo isolado por empresa (company_id).
"""
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime, ForeignKey, Enum, Boolean, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.enums import DocumentType, SignatureType


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Document(Base):
    """Um documento do dossier, com texto integral legível no ecrã."""
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    doc_type: Mapped[DocumentType] = mapped_column(
        Enum(DocumentType), default=DocumentType.OUTRO, nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)  # texto integral

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class DocumentRead(Base):
    """
    Registo de que um colaborador abriu/leu um documento.
    Cada par (documento, colaborador) regista a primeira leitura com carimbo.
    """
    __tablename__ = "document_reads"
    __table_args__ = (
        UniqueConstraint("document_id", "user_id", name="uq_read_document_user"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    read_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class Signature(Base):
    """
    Uma assinatura digital de adesão (secção 2.2), registada com carimbo temporal.
    Cada colaborador assina cada tipo uma vez.
    """
    __tablename__ = "signatures"
    __table_args__ = (
        UniqueConstraint("user_id", "signature_type", name="uq_signature_user_type"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    signature_type: Mapped[SignatureType] = mapped_column(
        Enum(SignatureType), nullable=False
    )
    signed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
