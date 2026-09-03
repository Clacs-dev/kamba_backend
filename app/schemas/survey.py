"""
Schemas Pydantic — cultura organizacional (secção 6).
"""
from datetime import datetime
from pydantic import BaseModel, Field

from app.models.enums import SurveyStatus


class SurveyCreate(BaseModel):
    title: str = Field(..., min_length=2, max_length=200)
    dimensions: list[str] = Field(..., min_length=1)


class SurveyOut(BaseModel):
    id: int
    company_id: int
    title: str
    dimensions: list[str]
    status: SurveyStatus
    created_at: datetime


class SurveyResponseSubmit(BaseModel):
    answers: dict[str, int]


class SurveyResults(BaseModel):
    survey_id: int
    response_count: int
    released: bool
    results: dict[str, float]
    note: str
    participation_count: int = 0
    universe: int = 0
    participation_rate: float | None = None


# --- Evolução das dimensões por ciclo (calculada das respostas reais) ---

class DimensionCyclePoint(BaseModel):
    """Percentagem de uma dimensão num ciclo (calculada das respostas)."""
    survey_id: int
    cycle_label: str   # título do pulse/ciclo
    value: float | None  # % (0..100) — None se a dimensão não foi medida nesse ciclo


class DimensionEvolution(BaseModel):
    """Uma dimensão e a sua percentagem em cada ciclo (uma coluna por ciclo)."""
    name: str
    points: list[DimensionCyclePoint]  # ordenado do mais antigo ao mais recente
    latest: float | None               # % do ciclo mais recente


class CultureDimensionsEvolution(BaseModel):
    """Evolução das dimensões de cultura através dos ciclos/pulses."""
    dimensions: list[DimensionEvolution] = []
    cycles: list[str] = []  # rótulos dos ciclos, na ordem de exibição
