"""
Schemas Pydantic — Percurso / linha do tempo (secção 2.3).
"""
from datetime import date, datetime
from pydantic import BaseModel, Field

from app.models.enums import CareerEventType


class CareerEventCreate(BaseModel):
    collaborator_id: int
    event_type: CareerEventType = CareerEventType.OUTRO
    event_date: date
    title: str = Field(..., min_length=2, max_length=200)
    description: str | None = None


class CareerEventOut(BaseModel):
    id: int
    company_id: int
    collaborator_id: int
    event_type: CareerEventType
    event_date: date
    title: str
    description: str | None
    created_at: datetime
    model_config = {"from_attributes": True}


class TimelineItem(BaseModel):
    """
    Um item da linha do tempo agregada. 'source' diz de onde veio o evento
    (manual, admissao, avaliacao, disciplina, exame...), para o frontend
    poder mostrar ícones/cores diferentes.
    """
    date: date
    source: str
    category: str
    title: str
    detail: str | None = None
