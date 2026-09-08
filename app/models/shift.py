"""
Modelo Shift — turnos configurados por uma empresa (alterações 8 e 9).

Só faz sentido quando `Company.uses_shifts` é True. Um colaborador em regime
de turno (`EmployeeProfile.work_schedule_type == TURNO`) associa-se a um
Shift via `EmployeeProfile.shift_id`. Pensado para, no futuro, alimentar um
módulo de assiduidade/presenças (ver comentário na secção 2.1 do manual).
"""
from datetime import datetime, time, timezone

from sqlalchemy import String, Boolean, DateTime, Time, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Shift(Base):
    __tablename__ = "shifts"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False
    )

    name: Mapped[str] = mapped_column(String(100), nullable=False)  # ex.: "Manhã", "Turno A"
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    break_start: Mapped[time | None] = mapped_column(Time, nullable=True)
    break_end: Mapped[time | None] = mapped_column(Time, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    def __repr__(self) -> str:
        return f"<Shift id={self.id} company_id={self.company_id} name={self.name!r}>"
