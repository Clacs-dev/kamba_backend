"""
Trilha de auditoria (secção 1.1 e capítulo 7).

Regista os atos relevantes praticados na plataforma — quem, o quê, quando —
para a Administração poder auditar. O manual valoriza a "prova documental de
cada ato", e esta trilha sustenta essa exigência.

Isolamento por company_id.
"""
from datetime import datetime, timezone

from sqlalchemy import String, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )
    # Quem praticou o ato (guardamos id e nome, para o registo sobreviver mesmo
    # que o utilizador seja removido).
    actor_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_name: Mapped[str] = mapped_column(String(200), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(50), nullable=False)

    # O que aconteceu.
    action: Mapped[str] = mapped_column(String(100), nullable=False)   # ex.: "avaliacao.validada"
    detail: Mapped[str | None] = mapped_column(String(400), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
