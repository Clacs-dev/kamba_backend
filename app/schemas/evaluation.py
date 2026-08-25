"""
Schemas Pydantic — ciclo de avaliação (secção 3).
"""
from datetime import datetime, timezone
from pydantic import BaseModel, Field, computed_field, field_validator

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

class DefinedObjective(BaseModel):
    """Objetivo pactuado, definido pelo Capital Humano no início do ciclo."""
    description: str = Field(..., min_length=2, max_length=300)
    weight: float = Field(..., ge=0, le=100)


class EvaluationCreate(BaseModel):
    cycle_id: int
    collaborator_id: int
    director_id: int
    category: EvaluationCategory = EvaluationCategory.TECNICO
    objectives: list[DefinedObjective] = []


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
    cycle_adjusted: bool = False
    commission_decision: str | None
    objectives: list[DefinedObjective] = Field(default=[], validation_alias="defined_objectives")
    created_at: datetime
    updated_at: datetime

    @field_validator("objectives", mode="before")
    @classmethod
    def _parse_objectives(cls, v):
        if v is None or v == []:
            return []
        if isinstance(v, str):
            import json as _json
            try:
                return _json.loads(v)
            except Exception:
                return []
        return v

    model_config = {"from_attributes": True, "populate_by_name": True}

    @computed_field
    @property
    def appeal_overdue(self) -> bool:
        """True se há um prazo de recurso e já foi ultrapassado (e ainda em comissão)."""
        if self.appeal_deadline is None:
            return False
        if self.phase != EvaluationPhase.COMISSAO:
            return False
        agora = datetime.now(timezone.utc)
        prazo = self.appeal_deadline
        if prazo.tzinfo is None:
            prazo = prazo.replace(tzinfo=timezone.utc)
        return agora > prazo

    @computed_field
    @property
    def appeal_days_left(self) -> int | None:
        """Dias (corridos) até ao prazo do recurso; negativo se já passou. None se não aplicável."""
        if self.appeal_deadline is None or self.phase != EvaluationPhase.COMISSAO:
            return None
        agora = datetime.now(timezone.utc)
        prazo = self.appeal_deadline
        if prazo.tzinfo is None:
            prazo = prazo.replace(tzinfo=timezone.utc)
        return (prazo - agora).days


class EvaluationListOut(EvaluationOut):
    """Igual à saída de uma avaliação, mas com os nomes das pessoas (para as
    listas e dossiers, sem o frontend ter de pedir a lista de colaboradores)."""
    collaborator_name: str | None = None
    director_name: str | None = None
