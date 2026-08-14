"""
Schemas Pydantic — Planos Individuais de Desenvolvimento (secção 5).
"""
from datetime import datetime
from pydantic import BaseModel, Field

from app.models.enums import DevelopmentPlanStatus, DevelopmentActionStatus


class DevelopmentActionCreate(BaseModel):
    title: str = Field(..., min_length=2, max_length=200)
    description: str | None = None


class DevelopmentPlanCreate(BaseModel):
    collaborator_id: int
    year: int = Field(..., ge=2000, le=2100)
    actions: list[DevelopmentActionCreate] = []


class DevelopmentActionOut(BaseModel):
    id: int
    plan_id: int
    title: str
    description: str | None
    status: DevelopmentActionStatus
    created_at: datetime
    model_config = {"from_attributes": True}


class DevelopmentPlanOut(BaseModel):
    id: int
    company_id: int
    collaborator_id: int
    collaborator_name: str | None = None
    year: int
    status: DevelopmentPlanStatus
    actions: list[DevelopmentActionOut] = []
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
