"""
Schemas Pydantic — cultura organizacional (secção 6).
"""
from datetime import datetime
from pydantic import BaseModel, Field

from app.models.enums import SurveyStatus


class SurveyCreate(BaseModel):
    title: str = Field(..., min_length=2, max_length=200)
    # Dimensões a medir (o manual sugere confiança na liderança, clareza
    # estratégica, reconhecimento, colaboração, alinhamento com valores, e as
    # dimensões próprias de cada empresa).
    dimensions: list[str] = Field(..., min_length=1)


class SurveyOut(BaseModel):
    id: int
    company_id: int
    title: str
    dimensions: list[str]
    status: SurveyStatus
    created_at: datetime


class SurveyResponseSubmit(BaseModel):
    # dimensão -> valor 1..5
    answers: dict[str, int]


class SurveyResults(BaseModel):
    """
    Resultados agregados. Se houver menos de 5 respostas, results vem vazio e
    'released' é False, protegendo o anonimato (regra do manual).
    """
    survey_id: int
    response_count: int
    released: bool
    results: dict[str, float]  # dimensão -> média (só se released)
    note: str
    # Participação (calculada a partir das participações registadas e do
    # universo de colaboradores ativos) — secção 6.
    participation_count: int = 0
    universe: int = 0
    participation_rate: float | None = None
