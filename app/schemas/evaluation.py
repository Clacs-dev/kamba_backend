"""
Schemas Pydantic — ciclo de avaliação (secção 3).
"""
from datetime import datetime
from pydantic import BaseModel, Field

from app.models.enums import EvaluationPhase, EvaluationCategory


# --- Ciclo ---

class CycleCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=150)


class CycleOut(BaseModel):
    id: int
    company_id: int
    name: str
    is_open: bool
    created_at: datetime
    model_config = {"from_attributes": True}


# --- Avaliação: criação ---

class EvaluationCreate(BaseModel):
    cycle_id: int
    collaborator_id: int
    director_id: int
    category: EvaluationCategory = EvaluationCategory.TECNICO


# --- Respostas do formulário (blocos do 3.2) ---

class Objective(BaseModel):
    description: str = ""
    weight: float = Field(default=0, ge=0)          # peso do objetivo
    execution: float = Field(default=0, ge=0, le=100)  # % de execução


class FormAnswers(BaseModel):
    objectives: list[Objective] = []
    competencies: dict[str, int] = {}   # chave -> 1..5
    values: dict[str, bool] = {}        # chave -> Sim/Não


# --- Ações de transição ---

class AppealRequest(BaseModel):
    reason: str = Field(..., min_length=3)


class CommissionDecisionRequest(BaseModel):
    decision: str = Field(..., min_length=3)


# --- Saída ---

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
    appeal_deadline: datetime | None = None
    commission_decision: str | None
    created_at: datetime
    updated_at: datetime
    model_config = {"from_attributes": True}
