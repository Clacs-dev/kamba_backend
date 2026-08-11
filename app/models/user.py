"""
Modelo User — utilizador da plataforma.

Cada utilizador pertence a exactamente uma empresa (company_id) e tem um
perfil (role) que determina as suas competências. O par (company_id, email)
é único: o mesmo email pode existir em empresas diferentes, mas nunca
duplicado dentro da mesma empresa.
"""
from datetime import datetime, timezone

from sqlalchemy import String, Boolean, DateTime, ForeignKey, Enum, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import UserRole


def _now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        # Isolamento multi-tenant ao nível da unicidade: email único POR empresa.
        UniqueConstraint("company_id", "email", name="uq_user_company_email"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # --- Chave de tenant: liga o utilizador à sua empresa ---
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )

    # --- Identificação e credenciais ---
    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)

    # --- Perfil / permissões ---
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole), default=UserRole.COLABORADOR, nullable=False
    )

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Marca que o utilizador tem de trocar a password no próximo acesso
    # (por exemplo, colaboradores criados com password temporária).
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    # Relação inversa para a empresa.
    company: Mapped["Company"] = relationship(back_populates="users")

    # Ficha profissional (um-para-um). uselist=False torna a relação singular.
    profile: Mapped["EmployeeProfile"] = relationship(
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} role={self.role.value}>"
