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
    """Necessidade detetada automaticamente pelo sistema.

    Fonte 'avaliacao' (nota < 3,5) ou 'pid' (ação de desenvolvimento pendente).
    """
    collaborator_id: int
    collaborator_name: str
    last_score: float | None = None
    classification: str | None = None
    reason: str
    source: str = "avaliacao"


class ActionStatusUpdate(BaseModel):
    status: TrainingActionStatus


class MyTrainingActionOut(BaseModel):
    id: int
    plan_id: int
    plan_name: str
    title: str
    description: str | None
    source: TrainingSource
    status: TrainingActionStatus
    created_at: datetime
    model_config = {"from_attributes": True}
