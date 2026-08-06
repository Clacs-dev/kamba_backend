"""
Schemas Pydantic — Saúde Ocupacional (secção 2.7).
Só aptidão e datas; nunca dados clínicos.
"""
from datetime import date, datetime
from pydantic import BaseModel, Field

from app.models.enums import FitnessResult


class ExamCreate(BaseModel):
    collaborator_id: int
    fitness: FitnessResult
    exam_date: date
    next_exam_date: date | None = None
    restriction_note: str | None = Field(default=None, max_length=300)


class ExamOut(BaseModel):
    id: int
    company_id: int
    collaborator_id: int
    fitness: FitnessResult
    exam_date: date
    next_exam_date: date | None
    restriction_note: str | None
    created_at: datetime
    model_config = {"from_attributes": True}


class OverdueExam(BaseModel):
    collaborator_id: int
    collaborator_name: str
    last_exam_date: date
    next_exam_date: date
    days_overdue: int