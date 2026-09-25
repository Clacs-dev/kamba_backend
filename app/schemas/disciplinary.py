"""
Schemas Pydantic — processo disciplinar (secção 4).
"""
from datetime import datetime, date
from pydantic import BaseModel, Field, field_validator

from app.models.enums import DisciplinaryPhase, DisciplinaryOutcome, CommitteeRole


# Fase 1 — Instauração (referência gerada automaticamente pelo sistema).
class CommitteeMemberIn(BaseModel):
    """Colaborador escolhido para a comissão e o papel que nele recai."""
    user_id: int
    role: CommitteeRole


class ProcessCreate(BaseModel):
    accused_id: int
    imputed_facts: str = Field(..., min_length=3)
    disciplinary_record: str | None = None
    committee: list[CommitteeMemberIn]

    @field_validator("committee")
    @classmethod
    def _comissao_valida(cls, v: list[CommitteeMemberIn]) -> list[CommitteeMemberIn]:
        ids = [m.user_id for m in v]
        if len(ids) != 3 or len(set(ids)) != 3:
            raise ValueError("A comissão disciplinar tem de ter exactamente 3 membros distintos.")
        papeis = [m.role for m in v]
        if len(set(papeis)) != 3 or set(papeis) != set(CommitteeRole):
            raise ValueError("A comissão tem de ter um relator, um instrutor e um presidente da comissão.")
        return v


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
    committee: list[CommitteeMemberIn]

    @field_validator("committee")
    @classmethod
    def _comissao_valida(cls, v: list[CommitteeMemberIn]) -> list[CommitteeMemberIn]:
        ids = [m.user_id for m in v]
        if len(ids) != 3 or len(set(ids)) != 3:
            raise ValueError("A comissão disciplinar tem de ter exactamente 3 membros distintos.")
        papeis = [m.role for m in v]
        if len(set(papeis)) != 3 or set(papeis) != set(CommitteeRole):
            raise ValueError("A comissão tem de ter um relator, um instrutor e um presidente da comissão.")
        return v


class CommitteeMemberOut(BaseModel):
    id: int
    full_name: str
    role: CommitteeRole


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
