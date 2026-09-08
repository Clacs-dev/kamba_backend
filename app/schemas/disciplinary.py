"""
Schemas Pydantic — processo disciplinar (secção 4).
"""
from datetime import datetime, date
from pydantic import BaseModel, Field, field_validator

from app.models.enums import DisciplinaryPhase, DisciplinaryOutcome


# Fase 1 — Instauração
class ProcessCreate(BaseModel):
    accused_id: int
    reference: str = Field(..., min_length=1, max_length=100)
    imputed_facts: str = Field(..., min_length=3)
    disciplinary_record: str | None = None


# Fase 2 — Nota de culpa (instrutor emite)
class ChargeNoteRequest(BaseModel):
    charge_note: str = Field(..., min_length=3)
    preventive_suspension: bool = False


# Fase 3 — Defesa (trabalhador submete)
class DefenseRequest(BaseModel):
    defense_text: str = Field(..., min_length=1)


# Fase 4 — Decisão (instrutor emite)
class DecisionRequest(BaseModel):
    decision_text: str = Field(..., min_length=3)
    outcome: DisciplinaryOutcome


# Fase 2 (instrutor pode fixar prazo de defesa junto com a nota de culpa)
class DeadlineRequest(BaseModel):
    defense_deadline: date


# Comissão disciplinar (alteração 11) — exactamente 3 directores.
class CommitteeSetRequest(BaseModel):
    member_ids: list[int]

    @field_validator("member_ids")
    @classmethod
    def _exatamente_tres_distintos(cls, v: list[int]) -> list[int]:
        if len(set(v)) != 3:
            raise ValueError("A comissão disciplinar tem de ter exactamente 3 membros distintos.")
        return v


class CommitteeMemberOut(BaseModel):
    id: int
    full_name: str


class ProcessOut(BaseModel):
    id: int
    company_id: int
    accused_id: int
    instructor_id: int
    reference: str
    phase: DisciplinaryPhase
    imputed_facts: str
    disciplinary_record: str | None
    charge_note: str | None
    preventive_suspension: bool
    charge_ack_at: datetime | None
    defense_text: str | None
    defense_deadline: date | None
    defense_submitted_at: datetime | None
    decision_text: str | None
    outcome: DisciplinaryOutcome
    decision_ack_at: datetime | None
    created_at: datetime
    updated_at: datetime
    committee_members: list[CommitteeMemberOut] = []
    model_config = {"from_attributes": True}
