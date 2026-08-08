"""
Modelo de notificação (transversal — secção 1.1 e fluxos dos capítulos 3 e 4).

Uma notificação é um aviso dentro da plataforma, dirigido a um utilizador.
É criada automaticamente quando um evento exige a atenção de alguém (ex.:
o colaborador submeteu a autoavaliação -> notifica o director).

O frontend consulta as notificações por polling e mostra as não lidas.
Isolamento por company_id.
"""
from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Destinatário da notificação.
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    # Categoria livre para o frontend agrupar/encaminhar (ex.: "avaliacao",
    # "disciplina", "formacao"). E uma ligação opcional ao recurso relacionado.
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    link: Mapped[str | None] = mapped_column(String(300), nullable=True)

    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
