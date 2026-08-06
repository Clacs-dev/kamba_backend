"""
Schemas Pydantic — plano de formação (secção 5).
"""
from datetime import datetime
from pydantic import BaseModel, Field

from app.models.enums import TrainingSource, TrainingPlanStatus, TrainingActionStatus


class PlanCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)


class PlanOut(BaseModel):
    id: int
    company_id: int
    name: str
    status: TrainingPlanStatus
    created_at: datetime
    model_config = {"from_attributes": True}


class ActionCreate(BaseModel):
    collaborator_id: int
    title: str = Field(..., min_length=2, max_length=200)
    description: str | None = None


class ActionOut(BaseModel):
    id: int
    company_id: int
    plan_id: int
    collaborator_id: int
    title: str
    description: str | None
    source: TrainingSource
    status: TrainingActionStatus
    created_at: datetime
    model_config = {"from_attributes": True}


class TrainingNeed(BaseModel):
    collaborator_id: int
    collaborator_name: str
    last_score: float
    classification: str | None
    reason: str