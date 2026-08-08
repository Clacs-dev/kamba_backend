"""
Modelo do "relatório de cultura" — dados de cultura editados pelo Capital Humano.

O manual descreve o painel de cultura com dimensões (evolução por ano), eNPS e
participação. Estes indicadores consolidados são inseridos/editados pelo Capital
Humano da empresa (não são calculados automaticamente pelos pulses, que servem
para a recolha anónima corrente). Guardamos um registo por empresa.

Os dados flexíveis (dimensões por ano, série de eNPS) ficam em JSON, para o CH
poder estruturar como precisar. Isolamento por company_id.
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Text, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class CultureReport(Base):
    __tablename__ = "culture_reports"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    company_id: Mapped[int] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True, nullable=False, unique=True
    )

    # Indicadores gerais (texto livre curto, ex.: "+34", "79%").
    enps: Mapped[str | None] = mapped_column(String(50), nullable=True)
    participation: Mapped[str | None] = mapped_column(String(50), nullable=True)
    pulses_note: Mapped[str | None] = mapped_column(String(150), nullable=True)

    # Dados estruturados em JSON (guardados como texto):
    # dimensions: [{"name": "...", "y2023": 58, "y2024": 66, "y2025": 71}, ...]
    # recommendations: ["...", "...", "..."]
    dimensions_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendations_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
