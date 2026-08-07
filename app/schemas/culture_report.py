"""
Schemas Pydantic — relatório de cultura (editado pelo CH).
"""
from pydantic import BaseModel


class DimensionRow(BaseModel):
    name: str
    y2023: float | None = None
    y2024: float | None = None
    y2025: float | None = None


class CultureReportIn(BaseModel):
    enps: str | None = None
    participation: str | None = None
    pulses_note: str | None = None
    dimensions: list[DimensionRow] = []
    recommendations: list[str] = []


class CultureReportOut(BaseModel):
    enps: str | None = None
    participation: str | None = None
    pulses_note: str | None = None
    dimensions: list[DimensionRow] = []
    recommendations: list[str] = []