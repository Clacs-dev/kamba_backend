"""
Modelo de chat directo entre utilizadores (alteração 7).

Desenho deliberadamente simples, no mesmo espírito de `Notification`: sem
tabela `Conversation` separada — uma "conversa" é o par (sender, recipient)
dentro da mesma empresa, derivado nas queries em vez de materializado. O
frontend consulta por polling (mesmo padrão de `Notificacoes.tsx`), não há
push em tempo real — ver decisão de arquitectura no plano de implementação.

Isolamento por company_id, tal como o resto do projecto.
"""
from datetime import datetime, timezone

from sqlalchemy import Text, DateTime, ForeignKey, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        # Acelera "histórico entre A e B" e "conversas de A", que filtram
        # sempre por company_id + um dos dois lados do par.
        Index("ix_chat_messages_company_sender", "company_id", "sender_id"),
        Index("ix_chat_messages_company_recipient", "company_id", "recipient_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    sender_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    recipient_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)

    def __repr__(self) -> str:
        return f"<ChatMessage id={self.id} sender_id={self.sender_id} recipient_id={self.recipient_id}>"
