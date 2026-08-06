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