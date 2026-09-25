"""
Modelo EmployeeProfile — a ficha detalhada do colaborador (secção 2.1 do manual).

Está separada da tabela `users` de propósito: `users` guarda a conta de acesso
(email, password, perfil), enquanto `employee_profiles` guarda os dados
profissionais (número, admissão, vínculo, categoria, direção, local). Relação
um-para-um. Isto mantém a autenticação limpa e a ficha pode crescer sem tocar
no login.

Pertence sempre a uma empresa (company_id) — parte do isolamento multi-tenant.
"""
from datetime import datetime, date, time, timezone

from sqlalchemy import String, Text, DateTime, Date, Time, ForeignKey, Enum, UniqueConstraint, JSON, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.enums import ContractType, WorkScheduleType


def _now() -> datetime:
    return datetime.now(timezone.utc)


class EmployeeProfile(Base):
    __tablename__ = "employee_profiles"
    __table_args__ = (
        # Número de colaborador único DENTRO de cada empresa.
        UniqueConstraint("company_id", "employee_number", name="uq_profile_company_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    # Ligação ao utilizador (um-para-um) e à empresa (tenant).
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, index=True, nullable=False
    )
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # --- Campos da ficha (secção 2.1) ---
    employee_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    admission_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    contract_type: Mapped[ContractType | None] = mapped_column(
        Enum(ContractType), nullable=True
    )
    contract_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)   # obrigatório quando contract_type == TERMO_CERTO (alteração 5)
    job_category: Mapped[str | None] = mapped_column(String(150), nullable=True)  # categoria profissional
    job_title: Mapped[str | None] = mapped_column(String(150), nullable=True)     # cargo específico (ex.: Chefe de Vendas)
    department: Mapped[str | None] = mapped_column(String(150), nullable=True)    # direção / área
    workplace: Mapped[str | None] = mapped_column(String(150), nullable=True)     # local de trabalho
    work_schedule: Mapped[str | None] = mapped_column(String(200), nullable=True) # horário em texto livre (legado — mantido por compatibilidade)

    # --- Horário estruturado (alterações 8 e 9) ---
    work_schedule_type: Mapped[WorkScheduleType | None] = mapped_column(Enum(WorkScheduleType), nullable=True)
    fixed_entry_time: Mapped[time | None] = mapped_column(Time, nullable=True)    # regime FIXO: hora de entrada
    fixed_exit_time: Mapped[time | None] = mapped_column(Time, nullable=True)     # regime FIXO: hora de saída
    fixed_break_start: Mapped[time | None] = mapped_column(Time, nullable=True)   # regime FIXO: início do intervalo
    fixed_break_end: Mapped[time | None] = mapped_column(Time, nullable=True)     # regime FIXO: fim do intervalo
    shift_id: Mapped[int | None] = mapped_column(
        ForeignKey("shifts.id", ondelete="SET NULL"), nullable=True
    )  # regime TURNO: turno da empresa a que o colaborador está associado

    situation_tags: Mapped[str | None] = mapped_column(String(300), nullable=True) # etiquetas livres, separadas por vírgula
    nationality: Mapped[str | None] = mapped_column(String(100), nullable=True)    # nacionalidade (ex.: Angolana)
    habilitacoes: Mapped[str | None] = mapped_column(String(200), nullable=True)  # habilitações literárias (ex.: Ensino Médio, Licenciatura)
    university: Mapped[str | None] = mapped_column(String(200), nullable=True)    # universidade de formação
    course: Mapped[str | None] = mapped_column(String(200), nullable=True)        # curso / habilitação académica
    birth_date: Mapped[date | None] = mapped_column(Date, nullable=True)          # data de nascimento (aniversários)
    birthday_notified_year: Mapped[int | None] = mapped_column(Integer, nullable=True)  # ano em que o aniversário já foi celebrado
    cv: Mapped[str | None] = mapped_column(Text, nullable=True)                   # CV livre — o RH digitaliza aqui
    education: Mapped[list | None] = mapped_column(JSON, nullable=True)           # formação académica: [{nivel, ano_inicio, ano_fim, pais, instituicao, curso, areas}, ...]
    experience: Mapped[list | None] = mapped_column(JSON, nullable=True)          # experiência de trabalho: [{onde, ano_inicio, ano_fim, funcao}, ...]
    certifications: Mapped[list | None] = mapped_column(JSON, nullable=True)      # cursos/certificações: [{nome, instituicao, data, certificado_url, validade}, ...] (alteração 10)
    photo_url: Mapped[str | None] = mapped_column(String(500), nullable=True)     # URL da foto do colaborador (Cloudinary)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    # Relação inversa para o utilizador.
    user: Mapped["User"] = relationship(back_populates="profile")

    def __repr__(self) -> str:
        return f"<EmployeeProfile user_id={self.user_id} number={self.employee_number!r}>"
