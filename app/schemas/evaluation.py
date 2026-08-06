"""
Schemas Pydantic — ciclo de avaliação (secção 3).
"""
from datetime import datetime
from pydantic import BaseModel, Field

from app.models.enums import EvaluationPhase, EvaluationCategory


class CycleCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)


class CycleOut(BaseModel):
    id: int
    company_id: int
    name: str
    is_open: bool
    created_at: datetime
    model_config = {"from_attributes": True}


class EvaluationCreate(BaseModel):
    cycle_id: int
    collaborator_id: int
    director_id: int
    category: EvaluationCategory = EvaluationCategory.TECNICO


class Objective(BaseModel):
    description: str = ""
    weight: float = Field(default=0, ge=0)
    execution: float = Field(default=0, ge=0, le=100)


class FormAnswers(BaseModel):
    objectives: list[Objective] = []
    competencies: dict[str, int] = {}
    values: dict[str, bool] = {}


class AppealRequest(BaseModel):
    reason: str = Field(..., min_length=3)


class CommissionDecisionRequest(BaseModel):
    decision: str = Field(..., min_length=3)


class EvaluationOut(BaseModel):
    id: int
    company_id: int
    cycle_id: int
    collaborator_id: int
    director_id: int
    category: EvaluationCategory
    phase: EvaluationPhase
    final_score: float | None
    classification: str | None
    appeal_reason: str | None
    commission_decision: str | None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}